"""Fetch a curated source manifest and extract article bodies for later cleaning.

HTML responses and extracted text stay in ignored local data directories.
The current project scope is text-only: no image downloads, OCR or visual
inference. This acquisition step does not produce clean_text or replace sample_v1.
"""

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

from lxml import html

from probe_sources import decode_body


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def get_response(source, cache, offline, refresh):
    path = cache / (source["doc_id"] + ".html")
    sidecar = path.with_suffix(".http.json")
    if path.exists() and sidecar.exists() and not refresh:
        body, meta = path.read_bytes(), json.loads(sidecar.read_text(encoding="utf-8"))
        if sha(body) != meta["response_sha256"]:
            raise ValueError("Cached response hash mismatch")
        return body, meta, True
    if offline:
        raise FileNotFoundError("Missing local snapshot: " + str(path))
    request = urllib.request.Request(source["source_url"], headers={
        "User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(6_000_001)
        if len(body) > 6_000_000:
            raise ValueError("Response exceeds 6 MB limit")
        if body.startswith(b"\x1f\x8b"):
            body = gzip.decompress(body)
        meta = {"source_url": source["source_url"], "final_url": response.url,
                "http_status": response.status, "collected_at": stamp(),
                "content_type": response.headers.get("Content-Type", ""),
                "declared_charset": response.headers.get_content_charset(),
                "response_sha256": sha(body), "response_bytes": len(body)}
    if meta["http_status"] != 200 or "/login" in meta["final_url"].lower():
        raise ValueError("Response is not a readable public article")
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    write_json(sidecar, meta)
    return body, meta, False


def extract_body(source, response_body, meta):
    decoded, encoding = decode_body(response_body, meta.get("declared_charset"))
    tree = html.fromstring(decoded, parser=html.HTMLParser(no_network=True))
    nodes = tree.xpath(source["body_xpath"])
    if len(nodes) != 1:
        raise ValueError("Expected one article body; found " + str(len(nodes)))
    container = copy.deepcopy(nodes[0])
    for xpath in source.get("exclude_xpaths", []):
        for node in list(container.xpath(xpath)):
            if node.getparent() is not None:
                node.drop_tree()
    for node in list(container.xpath(".//script|.//style|.//noscript")):
        node.drop_tree()
    raw_html = html.tostring(container, encoding="unicode", with_tail=False)
    image_count = len(container.xpath(".//img"))
    # Restore block boundaries without normalizing spelling, Unicode or whitespace.
    text_tree = copy.deepcopy(container)
    for node in text_tree.iter():
        if node.tag in ("div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"):
            node.tail = (node.tail or "") + "\n"
    raw_text = text_tree.text_content()
    compact = re.sub(r"\s+", " ", raw_text).strip()
    chinese = len(re.findall(r"[\u4e00-\u9fff]", raw_text))
    if chinese < 20 or "停止游记业务的运维" in raw_text:
        raise ValueError("Empty or contaminated article body")
    displayed_date = None
    if source["publisher"] == "携程攻略":
        headers = tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," journal_detail ")]')
        header_text = " ".join(text for node in headers for text in node.itertext())
        dates = re.findall(r"(?<!\d)(20\d\d)\.(\d\d)\.(\d\d)(?!\d)", header_text)
        if dates:
            displayed_date = "-".join(dates[0])
    else:
        dates = re.findall(r"(?:发布日期|发布时间)\s*[:：]?\s*(20\d\d-\d{2}-\d{2})", tree.text_content())
        if dates:
            displayed_date = dates[0]
    flags = list(source.get("review_flags", []))
    if source["text_type"] == "official_route" and len(compact) < 200:
        flags.append("short_official_route")
    if source["text_type"] == "tourist_note" and chinese < 800:
        flags.append("short_tourist_body_review")
    if "\u200b" in raw_text or "\ufeff" in raw_text or "\u200c" in raw_text:
        flags.append("invisible_unicode_present")
    if displayed_date and source.get("list_publication_date") and displayed_date != source["list_publication_date"]:
        flags.append("listing_detail_date_disagreement")
    paragraphs = [re.sub(r"\s+", " ", x).strip() for x in raw_text.splitlines()]
    duplicates = [p for p,n in Counter(p for p in paragraphs if len(p) >= 12).items() if n > 1]
    if duplicates:
        flags.append("repeated_paragraph_or_caption")
    record = dict(source)
    record.update(collected_at=meta["collected_at"], final_url=meta["final_url"],
                  http_status=meta["http_status"], response_sha256=meta["response_sha256"],
                  snapshot_encoding=encoding, detail_displayed_date=displayed_date,
                  content_scope="article_body_before_scenic_section_selection",
                  raw_html=raw_html, raw_text=raw_text,
                  image_element_count=image_count,
                  content_modality="text_only",
                  image_information_status="excluded_by_text_only_scope" if image_count else "not_applicable",
                  raw_text_sha256=sha(raw_text.encode("utf-8")),
                  review_flags=sorted(set(flags)), acquisition_status="raw_body_acquired")
    metrics = {"doc_id": source["doc_id"], "scenic_id": source["scenic_id"],
               "scenic_name": source["scenic_name"], "text_type": source["text_type"],
               "title": source["title"], "source_url": source["source_url"],
               "collected_at": meta["collected_at"], "http_status": meta["http_status"],
               "body_chars_without_whitespace": len(re.sub(r"\s+", "", raw_text)),
               "body_chinese_chars": chinese, "detail_displayed_date": displayed_date,
               "image_element_count": image_count,
               "image_information_status": record["image_information_status"],
               "list_publication_date": source.get("list_publication_date"),
               "published_at": source.get("published_at"),
               "response_sha256": meta["response_sha256"],
               "raw_text_sha256": record["raw_text_sha256"], "review_flags": record["review_flags"],
               "repeated_paragraph_or_caption_groups": len(duplicates), "status": "success"}
    return record, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/metadata/selected_v2_sources.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/downloads/selected_v2"))
    parser.add_argument("--raw-output", type=Path, default=Path("data/raw/full/selected_v2"))
    parser.add_argument("--report", type=Path, default=Path("data/metadata/selected_v2_acquisition_report.json"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()
    if args.offline and args.refresh:
        parser.error("--offline and --refresh cannot be combined")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    ids = [s["doc_id"] for s in sources]
    counts = Counter((s["scenic_id"],s["text_type"]) for s in sources)
    if (len(sources) != 30 or len(set(ids)) != 30 or len(counts) != 6
            or len({s["scenic_id"] for s in sources}) != 3
            or {s["text_type"] for s in sources} != {"official_route", "tourist_note"}
            or any(n != 5 for n in counts.values())):
        parser.error("Manifest must contain three scenic areas with 5 official routes and 5 tourist articles each")
    if any(not re.fullmatch(r"[A-Z0-9_]+", i) for i in ids):
        parser.error("Invalid document ID")
    results = []
    last_network_request = None
    for source in sources:
        cache_exists = (args.cache/(source["doc_id"]+".html")).exists() and (args.cache/(source["doc_id"]+".http.json")).exists()
        needs_network = not args.offline and (args.refresh or not cache_exists)
        if needs_network and last_network_request is not None:
            time.sleep(max(0, max(2.0, args.delay) - (time.monotonic()-last_network_request)))
        try:
            if needs_network:
                last_network_request = time.monotonic()
            body, meta, cached = get_response(source,args.cache,args.offline,args.refresh)
            record, metrics = extract_body(source,body,meta)
            write_json(args.raw_output/(source["doc_id"]+".json"),record)
        except Exception as error:
            metrics = {"doc_id": source["doc_id"], "status": "failed", "error": str(error)}
        results.append(metrics)
        print(source["doc_id"],metrics["status"],metrics.get("body_chars_without_whitespace", ""),flush=True)
    success = [r for r in results if r["status"] == "success"]
    hash_groups = {}
    for result in success:
        hash_groups.setdefault(result["raw_text_sha256"], []).append(result["doc_id"])
    summary = {"version": manifest["version"], "stage": "raw_acquisition_not_final_cleaning",
               "processing_scope": "text_only",
               "expected_documents": len(sources), "successful_documents": len(success),
               "failed_documents": len(results)-len(success),
               "total_body_chars_without_whitespace": sum(r["body_chars_without_whitespace"] for r in success),
               "exact_duplicate_body_groups": [group for group in hash_groups.values() if len(group)>1],
               "documents": results}
    write_json(args.report, summary)
    print("Acquired",len(success),"/",len(sources),flush=True)
    if len(success) != len(sources):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

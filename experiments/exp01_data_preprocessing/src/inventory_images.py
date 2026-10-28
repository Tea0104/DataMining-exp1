"""Inventory body images and optionally download selected images for inspection.

Context hints prioritize human review; they do not prove the image's contents.
This script performs no OCR and does not modify article text.
"""

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

from lxml import html


HINTS = ("路线图", "导览图", "导游图", "地图", "行程表", "时刻表", "站点图", "交通图", "价目表", "截图")


def compact(text, limit=240):
    return re.sub(r"\s+", " ", text).strip()[:limit]


def inventory(raw_dir):
    images = []
    documents = []
    for path in sorted(raw_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        tree = html.fromstring(record["raw_html"], parser=html.HTMLParser(no_network=True))
        root = tree.getroottree()
        nodes = tree.xpath(".//img")
        base = record.get("final_url") or record["source_url"]
        documents.append({"doc_id": record["doc_id"], "text_type": record["text_type"], "image_occurrences": len(nodes)})
        for ordinal, node in enumerate(nodes, 1):
            attrs = {k: v for k, v in node.attrib.items()
                     if k in ("src", "data-src", "data-original", "data-lazy-src", "srcset", "alt", "title", "width", "height", "data-id")}
            chosen_attr = next((k for k in ("data-original", "data-src", "data-lazy-src", "src") if node.get(k) and not node.get(k).startswith("data:")), None)
            url = urllib.parse.urljoin(base, node.get(chosen_attr)) if chosen_attr else None
            if url and urllib.parse.urlparse(url).scheme not in ("http", "https"):
                url = None
            before = compact(" ".join(node.xpath("preceding::text()[normalize-space()][position() <= 3]")))
            after = compact(" ".join(node.xpath("following::text()[normalize-space()][position() <= 3]")))
            hint_text = " ".join([attrs.get("alt", ""), attrs.get("title", ""), before, after])
            hints = [term for term in HINTS if term in hint_text]
            priority = "official_route_image" if record["text_type"] == "official_route" else "text_or_route_context_hint" if hints else "ordinary_image_pending_review"
            images.append({"image_id": f'{record["doc_id"]}_IMG_{ordinal:03d}',
                           "doc_id": record["doc_id"], "text_type": record["text_type"],
                           "source_page_url": record["source_url"], "ordinal_in_article": ordinal,
                           "xpath_in_raw_html": root.getpath(node), "url_attributes": attrs,
                           "chosen_url_attribute": chosen_attr, "image_url": url,
                           "nearby_text_before": before, "nearby_text_after": after,
                           "context_hints": hints, "review_priority": priority,
                           "visual_review_status": "not_reviewed", "ocr_status": "not_run",
                           "verified_text": None})
    return documents, images


def download(image_record, cache):
    image_url = image_record["image_url"]
    if not image_url:
        return {"status": "failed", "error": "No public HTTP(S) image URL found"}
    request = urllib.request.Request(image_url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": image_record["source_page_url"]})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(15_000_001)
        if len(body) > 15_000_000:
            raise ValueError("Image exceeds the 15 MB inspection limit")
        content_type = response.headers.get_content_type()
        if response.status != 200:
            raise ValueError("Image request did not return HTTP 200")
        final_url = response.url
    # Some valid image stores return application/octet-stream. Verify the actual
    # image format instead of accepting or rejecting solely by Content-Type.
    # Pillow is optional and only required when downloading inspection samples.
    from PIL import Image
    with Image.open(BytesIO(body)) as picture:
        width, height = picture.size
        suffix = "." + (picture.format or "img").lower().replace("jpeg", "jpg")
        picture.verify()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (image_record["image_id"] + suffix)
    path.write_bytes(body)
    return {"status": "success", "local_path": path.as_posix(), "final_url": final_url,
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
            "content_type": content_type, "width": width, "height": height}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/full/selected_v2"))
    parser.add_argument("--output", type=Path, default=Path("data/metadata/selected_v2_image_inventory.json"))
    parser.add_argument("--context-output", type=Path, default=Path("data/downloads/selected_v2_image_context.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/downloads/selected_v2_images"))
    parser.add_argument("--download", action="append", default=[], help="Download this image ID; repeat for several images")
    args = parser.parse_args()
    documents, images = inventory(args.raw_dir)
    if not documents:
        parser.error("No acquired article records found")
    by_id = {r["image_id"]: r for r in images}
    missing = set(args.download) - set(by_id)
    if missing:
        parser.error("Unknown image IDs: " + ", ".join(sorted(missing)))
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        for previous_image in previous.get("images", []):
            current = by_id.get(previous_image["image_id"])
            if current and current["image_url"] == previous_image["image_url"]:
                for key in ("download", "visual_review_status", "ocr_status", "verified_text"):
                    if key in previous_image:
                        current[key] = previous_image[key]
    for i, image_id in enumerate(dict.fromkeys(args.download)):
        if i:
            time.sleep(2)
        try:
            by_id[image_id]["download"] = download(by_id[image_id], args.cache)
        except Exception as error:
            by_id[image_id]["download"] = {"status": "failed", "error": str(error)}
        print(image_id, by_id[image_id]["download"]["status"], flush=True)
    summary = {"article_count": len(documents), "articles_with_images": sum(bool(r["image_occurrences"]) for r in documents),
               "image_occurrences": len(images), "distinct_url_count": len({r["image_url"] for r in images if r["image_url"]}),
               "official_image_occurrences": sum(r["text_type"] == "official_route" for r in images),
               "tourist_image_occurrences": sum(r["text_type"] == "tourist_note" for r in images),
               "priority_counts": dict(Counter(r["review_priority"] for r in images)),
               "downloaded_samples": sum(r.get("download", {}).get("status") == "success" for r in images),
               "assistant_visually_reviewed_samples": sum(r.get("visual_review_status") == "reviewed_by_assistant_vision" for r in images),
               "note": "Counts refer to img elements in saved article bodies. Context hints are unverified; distinct URLs are not pixel-level deduplication. OCR has not been run."}
    # Nearby article text is working material, not public source-index metadata.
    contexts = [{"image_id": r["image_id"], "nearby_text_before": r["nearby_text_before"],
                 "nearby_text_after": r["nearby_text_after"]} for r in images]
    public_images = [{k:v for k,v in r.items() if k not in ("nearby_text_before", "nearby_text_after")} for r in images]
    args.context_output.parent.mkdir(parents=True, exist_ok=True)
    args.context_output.write_text(json.dumps(contexts, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "documents": documents, "images": public_images}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

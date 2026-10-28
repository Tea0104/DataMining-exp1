"""Low-volume public-page probes; availability evidence, not a dataset collector.

Run from the repository root. Page responses stay in the ignored download cache.
All text-length metrics describe the whole HTML page, not its article body.
"""

import argparse
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
        self.links = []
        self.current = None
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.current = [attrs.get("href", ""), []]
        if tag in ("p", "div", "li", "h1", "h2", "h3", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.current:
            self.links.append({"href": self.current[0], "text": "".join(self.current[1]).strip()})
            self.current = None

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.skip:
            self.parts.append(data)
            if self.current:
                self.current[1].append(data)


def decode_body(body, declared):
    encodings = [declared] if declared else []
    match = re.search(br'charset\s*=\s*["\x27]?([\w-]+)', body[:10000], re.I)
    if match:
        encodings.append(match.group(1).decode("ascii"))
    encodings.extend(["utf-8", "gb18030"])
    for encoding in dict.fromkeys(encodings):
        try:
            return body.decode(encoding), encoding
        except (UnicodeError, LookupError):
            pass
    return body.decode("utf-8", errors="replace"), "utf-8-replacement"


def probe(target, output):
    result = dict(target)
    result["checked_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    start = time.monotonic()
    request = urllib.request.Request(target["url"], headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(6_000_001)
            if len(body) > 6_000_000:
                raise ValueError("Response exceeds the 6 MB probe limit")
            if body.startswith(b"\x1f\x8b"):
                body = gzip.decompress(body)
            result.update(http_status=response.status, final_url=response.url, bytes=len(body),
                          content_type=response.headers.get("Content-Type", ""))
            declared = response.headers.get_content_charset()
        text, result["encoding"] = decode_body(body, declared)
        page = Page()
        page.feed(text)
        visible = re.sub(r"\s+", " ", "".join(page.parts)).strip()
        result["title"] = "".join(page.title).strip()
        result["whole_page_text_chars"] = len(visible)
        result["whole_page_chinese_chars"] = len(re.findall(r"[\u4e00-\u9fff]", visible))
        result["body_sha256"] = hashlib.sha256(body).hexdigest()
        result["login_signals"] = [s for s in ("登录后", "扫码登录", "手机号登录") if s in visible]
        result["block_signals"] = [s for s in ("Access Denied", "验证码", "人机验证", "访问过于频繁") if s.lower() in text.lower()]
        seen = set()
        result["links"] = []
        for link in page.links:
            absolute = urllib.parse.urljoin(result["final_url"], link["href"])
            if absolute.startswith(("http://", "https://")) and absolute not in seen:
                seen.add(absolute)
                result["links"].append({"url": absolute, "text": link["text"]})
        result["review_status"] = "needs_body_and_scope_review"
        if "/login" in result["final_url"] or result["login_signals"]:
            result["review_status"] = "check_login_gate"
        if not visible or "页面不存在" in result["title"]:
            result["review_status"] = "empty_or_error_page"
        if target["kind"] == "robots":
            result["review_status"] = "inspect_directives_manually"
        (output / "responses" / (target["id"] + ".html")).write_text(text, encoding="utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeError, ValueError, OSError) as error:
        result["review_status"] = "request_failed"
        result["error"] = str(error)
        if isinstance(error, urllib.error.HTTPError):
            result["http_status"] = error.code
    result["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/metadata/source_probe_targets_20261028.json"))
    parser.add_argument("--output", type=Path, default=Path("data/downloads/source_probe"))
    parser.add_argument("--only", action="append", help="Probe only this ID; repeat to select several IDs")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between requests, minimum 2")
    args = parser.parse_args()
    targets = json.loads(args.manifest.read_text(encoding="utf-8"))
    if any(not re.fullmatch(r"[a-z0-9_]+", t["id"]) for t in targets):
        parser.error("Manifest IDs must contain only lowercase letters, digits and underscores")
    if args.only:
        missing = set(args.only) - {t["id"] for t in targets}
        if missing:
            parser.error("Unknown IDs: " + ", ".join(sorted(missing)))
        targets = [t for t in targets if t["id"] in args.only]
    (args.output / "responses").mkdir(parents=True, exist_ok=True)
    results = []
    for index, target in enumerate(targets):
        if index:
            time.sleep(max(2.0, args.delay))
        result = probe(target, args.output)
        results.append(result)
        (args.output / "probe_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(target["id"], result.get("http_status", "no_status"), result["review_status"])


if __name__ == "__main__":
    main()

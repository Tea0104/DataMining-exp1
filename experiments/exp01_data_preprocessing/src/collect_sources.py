"""Download candidate source responses separately from curated sample snapshots."""

import argparse
from datetime import datetime, timezone, timedelta
import gzip
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[3]


def collect(output, only=None):
    sources = json.loads((ROOT / 'data/metadata/sources.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=True)
    statuses = []
    for source in sources:
        if only and source['doc_id'] != only:
            continue
        status = {'doc_id': source['doc_id'], 'url': source['fetch_url'],
                  'attempted_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}
        payload = urllib.parse.urlencode(source.get('request_data', {})).encode() if source['request_method'] == 'POST' else None
        request = urllib.request.Request(source['fetch_url'], data=payload, method=source['request_method'],
                                         headers={'User-Agent': 'Mozilla/5.0', 'Referer': source['source_url'], 'X-Requested-With': 'XMLHttpRequest'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                if body.startswith(b'\x1f\x8b'):
                    body = gzip.decompress(body)
                encoding = response.headers.get_content_charset() or 'utf-8'
                text = body.decode(encoding, errors='strict')
                status.update(http_status=response.status, bytes=len(body))
            is_blocked = bool(re.search(r'var\s+arg1\s*=|acw_sc__|访问验证|验证码|错误请求|Access Denied|Just a moment', text[:16000], re.I))
            if is_blocked:
                status['result'] = 'blocked_or_error_page'
            elif source['request_method'] == 'POST':
                data = json.loads(text)
                if data.get('code') != 1 or not data.get('data', {}).get('description'):
                    raise ValueError('The official guide response has no route description')
                # Keep only the guide content. Omit any temporary response token.
                saved = json.dumps(data['data'], ensure_ascii=False, indent=2)
                (output / f"{source['doc_id']}.json").write_text(saved, encoding='utf-8')
                status['result'] = 'downloaded_candidate_needs_review'
            else:
                (output / f"{source['doc_id']}.html").write_text(text, encoding='utf-8')
                status['result'] = 'downloaded_candidate_needs_review'
        except (OSError, UnicodeError, ValueError, urllib.error.URLError) as error:
            status.update(result='request_failed', error=str(error))
        statuses.append(status)
        print(json.dumps(status, ensure_ascii=False))
    if only and not statuses:
        raise ValueError(f'Unknown doc_id: {only}')
    (output / 'fetch_status.json').write_text(json.dumps(statuses, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/downloads')
    parser.add_argument('--only', help='Download only one doc_id')
    args = parser.parse_args()
    collect(args.output_dir, args.only)

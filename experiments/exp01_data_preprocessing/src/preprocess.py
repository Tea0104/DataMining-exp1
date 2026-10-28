"""Build the shared sample from curated source snapshots. Python standard library only."""

import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
BLOCKS = {'p', 'div', 'article', 'section', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'br'}
SKIP = {'script', 'style', 'iframe', 'noscript'}


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip_depth += 1
        if not self.skip_depth and tag in BLOCKS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        if not self.skip_depth and tag in BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def text_from_html(fragment):
    parser = BodyText()
    parser.feed(fragment)
    parser.close()
    return ''.join(parser.parts)


def clean_text(text):
    """Remove body URLs and technical noise without rewriting the author's wording."""
    text = unicodedata.normalize('NFC', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\ufeff', '').replace('\u200b', '').replace('\u00a0', ' ')
    text = re.sub(r'https?://[^\s<>\u3000-\u303f\u4e00-\u9fff]+', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    lines = [re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n')]
    return '\n'.join(line for line in lines if line).strip()


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run(raw_dir, processed_dir, metadata_dir):
    files = sorted(raw_dir.glob('*.json'))
    if not files:
        raise ValueError(f'No source records found: {raw_dir}')
    records, sources, details = [], [], []
    for path in files:
        source = json.loads(path.read_text(encoding='utf-8'))
        raw = text_from_html(source['raw_html'])
        cleaned = clean_text(raw)
        record = {k: v for k, v in source.items() if k not in {'raw_html', 'fetch_url', 'request_method', 'request_data'}}
        record.update(raw_text=raw, clean_text=cleaned)
        records.append(record)
        sources.append({**{k: v for k, v in source.items() if k != 'raw_html'},
                        'snapshot_path': path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                        'raw_html_sha256': sha256(source['raw_html']),
                        'clean_text_sha256': sha256(cleaned)})
        details.append({'doc_id': record['doc_id'], 'scenic_name': record['scenic_name'],
                        'text_type': record['text_type'], 'raw_chars': len(raw), 'clean_chars': len(cleaned),
                        'removed_chars': len(raw) - len(cleaned),
                        'time_expression_hits': len(re.findall(r'上午|中午|下午|早上|傍晚|晚上|日出|日落|小时|半天|一日|一天', cleaned)),
                        'pronoun_or_demonstrative_hits': len(re.findall(r'它们|他们|她们|这里|那里|此处|这座|它|他|她', cleaned)),
                        'condition_or_advice_hits': len(re.findall(r'如果|假如|如体力|若|建议|推荐|可以|考虑到|要是', cleaned))})

    ids = [r['doc_id'] for r in records]
    pair_counts = Counter((r['scenic_id'], r['text_type']) for r in records)
    required = ['doc_id', 'scenic_id', 'scenic_name', 'text_type', 'title', 'source_url', 'publisher', 'clean_text', 'raw_text', 'license']
    checks = {
        'six_records': len(records) == 6,
        'three_scenic_areas': len({r['scenic_id'] for r in records}) == 3,
        'one_official_and_one_tourist_per_scenic': len(pair_counts) == 6 and all(n == 1 for n in pair_counts.values()) and {t for _, t in pair_counts} == {'official_route', 'tourist_note'},
        'unique_doc_ids': len(ids) == len(set(ids)),
        'required_fields_nonempty': all(all(r.get(k) for k in required) for r in records),
        'no_exact_duplicate_clean_text': len({sha256(r['clean_text']) for r in records}) == len(records),
        'no_replacement_characters': all('\ufffd' not in r['clean_text'] for r in records),
        'no_html_or_script_noise': all(not re.search(r'<(?:script|style|p|div|article)\b|arg1=|document\.cookie', r['clean_text'], re.I) for r in records),
        'no_body_urls': all(not re.search(r'https?://', r['clean_text']) for r in records),
        'normalization_idempotent': all(clean_text(r['clean_text']) == r['clean_text'] for r in records),
    }
    if not all(checks.values()):
        raise ValueError(f'Validation failed: {checks}')

    write_json(processed_dir / 'sample_v1.json', records)
    (processed_dir / 'sample_v1.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
    text_dir = processed_dir / 'texts'
    text_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        (text_dir / f"{record['doc_id']}.txt").write_text(record['clean_text'], encoding='utf-8')
    write_json(metadata_dir / 'sources.json', sources)
    quality = {'dataset_version': 'sample_v1', 'record_count': len(records),
               'total_clean_chars': sum(len(r['clean_text']) for r in records),
               'checks': checks, 'records': details,
               'limitations': ['开发样本，不是完整实验语料或独立评估集。',
                              '黄山官方及西湖官方转载来源使用搜索索引核验片段，直接访问分别遇到HTTP 412和脚本校验页。',
                              '西湖官方来源是官方发布内容的新闻网站转载，已与官网第一手来源区分。',
                              '路线和游客游记取用范围不完全相同；时间、条件、共指样本分布不均。',
                              '诊断命中数只是触发词计数，不是实体、共指标注数量或抽取准确率。',
                              '原文误字、口语、图注、未到访地点和周边地点保留，需后续模块判断。']}
    write_json(metadata_dir / 'quality_report.json', quality)
    report = ['# 开发样本质量检查', '', '数据版本：sample_v1。3 个景区、6 条文本，各有 1 条官方路线和 1 篇游客游记的选定正文。', '',
              '| 文本编号 | 景区 | 类型 | 原始字符数 | 清洗后字符数 |', '|---|---|---|---:|---:|']
    report += [f"| {d['doc_id']} | {d['scenic_name']} | {d['text_type']} | {d['raw_chars']} | {d['clean_chars']} |" for d in details]
    report += ['', '## 完整性检查', ''] + [f"- {key}：{'通过' if val else '未通过'}" for key, val in checks.items()]
    report += ['', '## 使用限制', ''] + ['- ' + note for note in quality['limitations']]
    report += ['', '清洗剥离HTML标签、过滤脚本和样式、移除正文网址、归一化换行空白及技术性控制符。来源URL保留在元数据，raw_text保留原始正文网址。景点原名、时间、条件、代词、序号和路线连接符保持原文，不自动补写或纠错。', '']
    (metadata_dir / 'quality_report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps({'records': len(records), 'scenic_areas': 3, 'clean_chars': quality['total_clean_chars'], 'checks': checks}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, default=ROOT / 'data/raw/sample_v1')
    parser.add_argument('--processed-dir', type=Path, default=ROOT / 'data/processed')
    parser.add_argument('--metadata-dir', type=Path, default=ROOT / 'data/metadata')
    args = parser.parse_args()
    run(args.raw_dir, args.processed_dir, args.metadata_dir)

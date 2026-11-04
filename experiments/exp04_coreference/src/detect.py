"""检测第三人称和指示代词；最长匹配并保留每次出现的位置。"""
import argparse
import re
from collections import Counter

from common import DATASET, DEFAULT_DOCS, OUTPUTS, load_records, sentences, span, text_hash, write_json

PRONOUNS = ('他们', '她们', '它们', '这里', '那里', '这儿', '那儿', '这边', '那边',
            '此处', '此地', '该处', '该园', '该景区', '这些', '那些', '这个', '那个',
            '它', '他', '她', '这', '那', '此', '该')
PATTERN = re.compile('|'.join(re.escape(p) for p in sorted(PRONOUNS, key=len, reverse=True)))


def detect_record(record):
    text = record['clean_text']
    sents = sentences(text)
    output = []
    for match in PATTERN.finditer(text):
        word, start, end = match.group(), match.start(), match.end()
        before, after = text[max(0, start - 1):start], text[end:end + 1]
        if word in ('他', '它') and (before == '其' or after == '人'):
            continue  # 其他/其它/他人不是第三人称回指。
        if word in ('这', '那') and after in ('么', '样'):
            continue  # 方式副词不纳入本轮实体/事件回指任务。
        if word == '此' and (before == '因' or after == '外'):
            continue
        if word == '该' and before in ('应', '活'):
            continue
        sentence = next(s for s in sents if s['start'] <= start < s['end'])
        kind = ('person' if word in ('他', '他们', '她', '她们') else
                'thing_or_animal' if word in ('它', '它们') else
                'location' if word in ('这里', '那里', '这儿', '那儿', '这边', '那边',
                                     '此处', '此地', '该处', '该园', '该景区') else 'demonstrative')
        output.append({
            'sample_id': f"{record['doc_id']}:{start}:{end}",
            'doc_id': record['doc_id'], 'scenic_id': record['scenic_id'],
            'source_url': record.get('source_url'), 'pronoun': span(text, start, end),
            'pronoun_type': kind, 'sentence': sentence,
            'context': span(text, max(0, start - 220), min(len(text), end + 120)),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=str, default=str(DATASET))
    parser.add_argument('--docs', nargs='+', default=list(DEFAULT_DOCS), help='文档编号；all 表示全部')
    parser.add_argument('--outputs', type=str, default=str(OUTPUTS))
    args = parser.parse_args()
    records = load_records(args.input)
    selected = records if args.docs == ['all'] else [r for r in records if r['doc_id'] in args.docs]
    if args.docs != ['all'] and set(args.docs) != {r['doc_id'] for r in selected}:
        parser.error('存在未知文档编号')
    items = [sample for record in selected for sample in detect_record(record)]
    from pathlib import Path
    outputs = Path(args.outputs)
    write_json(outputs / 'samples.json', items)
    write_json(outputs / 'detection_stats.json', {
        'documents': len(selected), 'samples': len(items), 'scope': 'third_person_and_demonstratives',
        'by_doc': {r['doc_id']: sum(s['doc_id'] == r['doc_id'] for s in items) for r in selected},
        'by_pronoun': dict(Counter(s['pronoun']['text'] for s in items)),
        'by_scenic': dict(Counter(s['scenic_id'] for s in items)),
        'source_text_sha256': {r['doc_id']: text_hash(r['clean_text']) for r in selected},
        'note': '命中数量不是消解正确数量；时间指示、后指和语境外指示也保留供标注。'})
    print(f'detected: {len(selected)} documents, {len(items)} pronoun occurrences')


if __name__ == '__main__':
    main()

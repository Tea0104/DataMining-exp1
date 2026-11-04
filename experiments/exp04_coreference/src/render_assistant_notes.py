"""将剩余文章的助手解释直接标在原文中，不改变人工标注或程序预测。"""
import argparse
from collections import Counter, defaultdict
from pathlib import Path

from common import BASE, DATASET, OUTPUTS, load_records, read_json, text_hash, validate_span, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--annotations', type=Path, default=BASE / 'annotations/remaining25_assistant_draft.json')
    parser.add_argument('--outputs', type=Path, default=OUTPUTS / 'remaining25')
    args = parser.parse_args()
    annotation = read_json(args.annotations)
    records = {r['doc_id']: r for r in load_records(args.input)}
    grouped = defaultdict(list)
    ids = set()
    for item in annotation['items']:
        if item['sample_id'] in ids:
            raise ValueError('助手标注存在重复样本')
        ids.add(item['sample_id'])
        text = records[item['doc_id']]['clean_text']
        validate_span(text, item['pronoun'])
        for evidence in item['supporting_text_spans']:
            validate_span(text, evidence)
            if evidence['end'] > item['pronoun']['start']:
                raise ValueError('支持片段必须来自前文')
        if item['review_status'] != 'pending' or item['reviewer'] is not None:
            raise ValueError('此文件应保持助手初标状态，不能作为已人工复核的标注导出')
        grouped[item['doc_id']].append(item)
    samples = read_json(args.outputs / 'samples.json')
    if ids != {s['sample_id'] for s in samples}:
        raise ValueError('助手说明未完整覆盖原检测样本')
    if set(annotation['scope_docs']) & set(annotation['excluded_human_reviewed_docs']):
        raise ValueError('范围混入此前人工复核文章')
    args.outputs.mkdir(parents=True, exist_ok=True)
    article_dir = args.outputs / 'assistant_articles'
    article_dir.mkdir(exist_ok=True)
    lines = ['# 剩余25篇原文的助手初标说明', '',
             '本文件直接解释原文中检测到的指代用法，与原程序预测分开保存。加粗的是候选词，后面的“补充编号”是助手对其含义的判断。', '',
             '这25篇未由用户人工复核，作为补充阅读材料，不作为人工金标，不计算准确率。此前五篇61项人工复核记录保持独立。', '',
             '依赖现场或图片、只作限定、不能唯一确定的地方已注明；没有强行把每一处都解释为前文的某个景点。', '']
    summaries = []
    for article_index, doc in enumerate(annotation['scope_docs'], 1):
        record = records[doc]
        if text_hash(record['clean_text']) != annotation['source_text_sha256'][doc]:
            raise ValueError('原文已变化，需重新核对助手说明')
        text = record['clean_text']
        for item in sorted(grouped[doc], key=lambda i: i['pronoun']['start'], reverse=True):
            pronoun = item['pronoun']
            marked = f"**{pronoun['text']}**【补充{item['number']}：{item['referent_description']}】"
            text = text[:pronoun['start']] + marked + text[pronoun['end']:]
        intro = [f"## 文章{article_index} {record['title']}", '',
                 f"编号：{doc}；共{len(grouped[doc])}处助手说明，未经人工复核。", '',
                 f"[原网页]({record.get('source_url', '')})", '']
        note = [] if grouped[doc] else ['', '本篇未检出当前词表范围内的候选词，完整原文仍保留。']
        page = intro + [text] + note
        (article_dir / f'{doc}.md').write_text('\n'.join(page).rstrip() + '\n', encoding='utf-8', newline='\n')
        lines += page + ['', '---', '']
        summaries.append({'doc_id': doc, 'title': record['title'], 'assistant_notes': len(grouped[doc]),
                          'human_reviewed': False})
    (args.outputs / 'assistant_annotations.md').write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8', newline='\n')
    write_json(args.outputs / 'assistant_annotations_summary.json', {
        'documents': len(annotation['scope_docs']), 'assistant_explanations': len(annotation['items']),
        'human_reviewed_items': 0, 'accuracy': None, 'reference_kind_counts': dict(Counter(i['reference_kind'] for i in annotation['items'])),
        'by_doc': summaries, 'note': '助手独立补充解释，不代表程序已产生这些答案，也不是人工金标。'})
    print(f"rendered: {len(summaries)} complete articles, {len(ids)} assistant explanations; human review count 0")


if __name__ == '__main__':
    main()

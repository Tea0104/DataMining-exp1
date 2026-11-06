"""合并两次独立抽取的候选，用全文复核，再以相同名称级口径评估。"""
import argparse
import json
import os
from pathlib import Path

from run import DATASET, HERE, REFERENCE, gold_set, nonoverlap, pred_set, prf, read, request_names, sha, write


def review(record, candidates, prompt, api_key, evidence='document'):
    grouped = {}
    text = record['clean_text']
    for entity in candidates:
        start, end = entity['start'], entity['end']
        if not 0 <= start < end <= len(text) or text[start:end] != entity['text']:
            raise ValueError(f"候选位置不匹配：{record['doc_id']}")
        grouped.setdefault(entity['text'], []).append(entity)
    names = list(grouped)
    audit, kept = [], []
    batch_size = 32 if evidence == 'document' else 12
    for start in range(0, len(names), batch_size):
        indexed = {str(i + 1): name for i, name in enumerate(names[start:start + batch_size])}
        content = f'目标景区：{record["scenic_name"]}\n'
        if evidence == 'document':
            content += f'整篇原文：\n{text}\n待复核候选：\n{json.dumps(indexed, ensure_ascii=False)}'
        else:
            cards = {}
            for i, name in indexed.items():
                spans = sorted({(e['start'], e['end']) for e in grouped[name]})
                sample = sorted({spans[0], spans[len(spans) // 2], spans[-1]})
                cards[i] = {'name': name, 'excerpts': [
                    text[max(0, left - 75):min(len(text), right + 75)]
                    for left, right in sample
                ]}
            content += f'待复核候选及其原文片段：\n{json.dumps(cards, ensure_ascii=False)}'
        rejected = request_names('https://api.deepseek.com/chat/completions', 'deepseek-flash',
                                 api_key, prompt, content)
        if not set(rejected) <= indexed.keys():
            raise ValueError(f"模型返回了未提供的候选编号：{record['doc_id']}")
        audit.append({'candidates': indexed, 'rejected_ids': rejected})
        kept.extend(e for i, name in indexed.items() if i not in rejected for e in grouped[name])
    return {'doc_id': record['doc_id'], 'entities': nonoverlap(kept), 'batches': audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs=2, help='两组已完成的独立抽取输出')
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--evidence', choices=('document', 'excerpts'), default='document')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    api_key = os.getenv('LLM_API_KEY')
    if not api_key:
        parser.error('请设置环境变量 LLM_API_KEY')
    manifests = [read(path / 'manifest.json') for path in args.runs]
    if manifests[0]['documents'] != manifests[1]['documents']:
        parser.error('两组抽取的文档范围不一致')
    input_hash = sha(args.input.read_bytes())
    if any(m['input_sha256'] != input_hash for m in manifests):
        parser.error('输入原文版本和抽取运行不一致')
    ids = set(manifests[0]['documents'])
    records = [r for r in read(args.input) if r['doc_id'] in ids]
    if len(records) != len(ids) or {r['doc_id'] for r in records} != ids:
        parser.error('找不到完整的复核文档')
    entities_by_doc = {doc_id: [] for doc_id in ids}
    for path in args.runs:
        for entity in read(path / 'llm_entities.json'):
            entities_by_doc[entity['doc_id']].append(entity)
    prompt = (HERE / 'document_review_prompt.txt').read_text(encoding='utf-8')
    if args.evidence == 'excerpts':
        prompt += ('\n实际输入为每个候选在正文中的局部原文。结合它的片段判断，'
                   '某一处明确作为合格名称使用就保留。片段证据不足时不要猜测候选不合格。')
    settings = {
        'model': 'deepseek-flash',
        'evidence': args.evidence,
        'input_sha256': input_hash,
        'documents': sorted(ids),
        'source_entities_sha256': [sha((p / 'llm_entities.json').read_bytes()) for p in args.runs],
        'prompt_sha256': sha(prompt.encode()),
        'runner_sha256': sha(Path(__file__).read_bytes()),
        'client_sha256': sha((HERE / 'run.py').read_bytes()),
    }
    ref = None
    if args.input.resolve() == DATASET.resolve():
        settings['reference_sha256'] = sha(REFERENCE.read_bytes())
        if any(m['reference_sha256'] != settings['reference_sha256'] for m in manifests):
            parser.error('参考标注版本和抽取运行不一致')
        ref = read(REFERENCE)
    out = args.output
    manifest = out / 'manifest.json'
    if manifest.exists() and read(manifest) != settings:
        parser.error('已有不同配置的运行，请换输出目录')
    docs = out / 'documents'
    docs.mkdir(parents=True, exist_ok=True)
    write(manifest, settings)
    results = []
    for record in records:
        doc_id = record['doc_id']
        if not doc_id or not all(c.isascii() and (c.isalnum() or c in '_-') for c in doc_id):
            raise ValueError(f'无效文档编号：{doc_id}')
        path = docs / f'{doc_id}.json'
        if not path.exists():
            result = review(record, entities_by_doc[doc_id], prompt, api_key, args.evidence)
            write(path, result)
        else:
            result = read(path)
        results.append(result)
        print(f'{doc_id} 复核完成，保留 {len(result["entities"])} 处', flush=True)
    final_entities = [e for result in results for e in result['entities']]
    write(out / 'llm_entities.json', final_entities)
    if ref:
        truth = {x for x in gold_set(ref) if x[0] in ids and x[1] == 'POI'}
        pred = pred_set(final_entities)
        score = prf(pred, truth)
        write(out / 'evaluation.json', {
            'documents': sorted(ids),
            'evaluation_level': 'document_type_surface_name',
            'reference_human_reviewed': ref['human_reviewed'],
            'requests': sum(len(result['batches']) for result in results),
            'candidate_names': len(pred_set(e for group in entities_by_doc.values() for e in group)),
            'scores': {'llm_document_review': {
                **score, 'missed': sorted(truth - pred), 'unmatched_predictions': sorted(pred - truth),
            }},
        })
        print(score, flush=True)


if __name__ == '__main__':
    main()

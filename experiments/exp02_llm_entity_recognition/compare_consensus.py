"""在两次已完成的评测中，比较两模型共同确认的 v7 补漏候选。"""
import argparse
from pathlib import Path

from run import BASE, REFERENCE, gold_set, nonoverlap, pred_set, prf, read, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', nargs=2, type=Path, help='两次不同模型的完整评测目录')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifests = [read(p / 'manifest.json') for p in args.runs]
    first, second = manifests
    if first['model'] == second['model']:
        parser.error('需要两个不同模型的评测')
    for field in ('documents', 'input_sha256', 'reference_sha256', 'baseline_sha256'):
        if first[field] != second[field]:
            parser.error(f'两次评测的 {field} 不一致')
    if first['reference_sha256'] != sha(REFERENCE.read_bytes()):
        parser.error('当前参考文件与评测版本不一致')
    ids = set(first['documents'])
    baseline = {doc_id: [] for doc_id in ids}
    for name, digest in first['baseline_sha256'].items():
        if name.endswith('_v7.json'):
            path = BASE / 'outputs' / name
            if sha(path.read_bytes()) != digest:
                parser.error(f'当前对照文件版本不一致：{name}')
            for entity in read(path):
                if entity['doc_id'] in ids:
                    baseline[entity['doc_id']].append(entity)

    combined = []
    for doc_id in sorted(ids):
        one, two = [
            read(path / 'documents' / f'{doc_id}.json')['v7_verification']['entities']
            for path in args.runs
        ]
        agreed = pred_set(one) & pred_set(two)
        # 取第二次评测中的原文跨度，并保留 v7 的全部实体。
        accepted = [e for e in two if pred_set([e]) <= agreed]
        combined.extend(nonoverlap(accepted, baseline[doc_id]))

    truth = {x for x in gold_set(read(REFERENCE)) if x[0] in ids and x[1] == 'POI'}
    v7 = pred_set(e for group in baseline.values() for e in group if e['entity_type'] == 'POI')
    pred = pred_set(e for e in combined if e['entity_type'] == 'POI')
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / 'v7_consensus_entities.json', combined)
    write(args.output / 'evaluation.json', {
        'models': [m['model'] for m in manifests],
        'input_manifest_sha256': [sha((p / 'manifest.json').read_bytes()) for p in args.runs],
        'documents': sorted(ids),
        'evaluation_level': 'document_type_surface_name',
        'scores': {'v7': prf(v7, truth), 'v7_plus_consensus': prf(pred, truth)},
        'added_matches': sorted((pred - v7) & truth),
        'added_unmatched_predictions': sorted(pred - v7 - truth),
    })
    print(prf(pred, truth), flush=True)


if __name__ == '__main__':
    main()

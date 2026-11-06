"""按名称级两票合并两组独立抽取和一次候选复核。"""
import argparse
from pathlib import Path

from run import REFERENCE, gold_set, nonoverlap, pred_set, prf, read, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extractions', nargs=2, type=Path)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source_paths = [p / 'llm_entities.json' for p in args.extractions]
    reviewed_path = args.review / 'llm_entities.json'
    manifest = read(args.review / 'manifest.json')
    digests = [sha(p.read_bytes()) for p in source_paths]
    if digests != manifest['source_entities_sha256']:
        parser.error('抽取产物与复核输入不一致')

    first, second = [read(p) for p in source_paths]
    reviewed = read(reviewed_path)
    one, two, review = map(pred_set, (first, second, reviewed))
    if not review <= one | two:
        parser.error('复核产物中有原始候选以外的名称')
    # 双提示均抽出的名称已有两票；仅被一种提示抽出的名称需要复核支持。
    kept_names = (one & two) | review
    by_doc = {doc_id: [] for doc_id in manifest['documents']}
    for entity in first + second:
        if pred_set([entity]) <= kept_names:
            by_doc[entity['doc_id']].append(entity)
    entities = [e for group in by_doc.values() for e in nonoverlap(group)]

    reference_hash = manifest.get('reference_sha256')
    if reference_hash and reference_hash != sha(REFERENCE.read_bytes()):
        parser.error('参考标注版本与复核不一致')
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / 'llm_entities.json', entities)
    write(args.output / 'manifest.json', {
        'documents': manifest['documents'],
        'source_entities_sha256': digests,
        'review_entities_sha256': sha(reviewed_path.read_bytes()),
        'reference_sha256': reference_hash,
        'rule': 'supported_by_both_extractors_or_review',
    })
    if reference_hash:
        truth = {x for x in gold_set(read(REFERENCE)) if x[0] in by_doc and x[1] == 'POI'}
        pred = pred_set(entities)
        score = prf(pred, truth)
        write(args.output / 'evaluation.json', {
            'documents': manifest['documents'],
            'evaluation_level': 'document_type_surface_name',
            'scores': {'llm_vote': {
                **score, 'missed': sorted(truth - pred), 'unmatched_predictions': sorted(pred - truth),
            }},
        })
        print(score, flush=True)


if __name__ == '__main__':
    main()

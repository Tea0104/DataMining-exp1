#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实验二：按名称级金标评估精确率、覆盖率与 F1（按景区分别评估）。

用法（仓库根目录运行）：

    python experiments/exp02_entity_recognition/src/evaluate.py
    python experiments/exp02_entity_recognition/src/evaluate.py --version v2 --scenic TAISHAN

金标按景区约定为 `outputs/gold_<SCENIC>.json`，格式同
`archive/sample_v1_huangshan/gold_huangshan.json`：
`{"items": [{"doc_id", "entity_type", "text"}, ...]}`。

缺少金标时**不报错**，只在终端提示并跳过该景区；全部缺失则说明本轮未评估。
有评估结果时写出 `outputs/evaluation_<version>.json`，evaluation.json 作为版本索引。
"""

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
OUTPUTS = SRC.parent / 'outputs'
VERSIONS = ('v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7')
TYPES = ('POI', 'TRANSPORT', 'TIME')
TYPE_CN = {'POI': '景点POI', 'TRANSPORT': '交通方式', 'TIME': '时间节点'}


def norm(text):
    return ''.join(text.split())


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def pred_set(entities):
    return {(e['doc_id'], e['entity_type'], norm(e['text'])) for e in entities}


def gold_set(gold):
    return {(item['doc_id'], item['entity_type'], norm(item['text'])) for item in gold['items']}


def prf(pred, gold):
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': round(precision, 4), 'recall': round(recall, 4), 'f1': round(f1, 4)}


def evaluate(version, scenic, gold_path, outputs=OUTPUTS):
    entities = load_json(outputs / f'entities_{scenic}_{version}.json')
    gold = load_json(gold_path)
    truth = gold_set(gold)
    doc_ids = set(gold.get('doc_scope', [item['doc_id'] for item in gold['items']]))
    if any(item['doc_id'] not in doc_ids for item in gold['items']):
        raise ValueError(f'金标条目超出 doc_scope: {gold_path}')
    pred_all = pred_set(entities)
    # 只在金标覆盖的文档上评估，避免未标文档的实体被算成误报
    pred = {x for x in pred_all if x[0] in doc_ids}
    result = {'version': version, 'scenic_id': scenic,
              'doc_scope': sorted(doc_ids),
              'prediction_names_in_scope': len(pred),
              'prediction_mentions_in_scope': sum(e['doc_id'] in doc_ids for e in entities),
              'gold_items': len(truth), 'gold_file': Path(gold_path).name,
              'overall': prf(pred, truth), 'by_type': {}}
    for entity_type in TYPES:
        p = {x for x in pred if x[1] == entity_type}
        g = {x for x in truth if x[1] == entity_type}
        result['by_type'][entity_type] = prf(p, g)
        result['by_type'][entity_type]['false_positive'] = sorted(x[2] for x in p - g)
        result['by_type'][entity_type]['false_negative'] = sorted(x[2] for x in g - p)
    result['errors'] = {
        label: [{'doc_id': d, 'entity_type': t, 'text': name}
                for d, t, name in sorted(values)]
        for label, values in [('predicted_only', pred - truth), ('gold_only', truth - pred)]}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='实验二：名称级评估（按景区）')
    parser.add_argument('--version', choices=VERSIONS, default='v2')
    parser.add_argument('--scenic', nargs='*', default=None,
                        help='默认取 outputs 下所有 entities_<景区>_<版本>.json')
    parser.add_argument('--gold', type=Path, default=None,
                        help='只评估一个景区时可直接指定金标文件')
    parser.add_argument('--outputs', type=Path, default=OUTPUTS)
    parser.add_argument('--dataset', type=Path,
                        default=SRC.parents[2] / 'data/processed/full/selected_v2/dataset.json')
    args = parser.parse_args(argv)

    if args.scenic:
        scenics = args.scenic
    else:
        scenics = sorted(p.stem[len('entities_'):-len(f'_{args.version}')]
                         for p in args.outputs.glob(f'entities_*_{args.version}.json'))
    if args.gold and len(scenics) != 1:
        parser.error('--gold 必须配合 --scenic 指定一个景区')
    if args.gold and len(scenics) == 1:
        gold_map = {scenics[0]: args.gold}
    else:
        gold_map = {s: args.outputs / f'gold_{s}.json' for s in scenics}

    results, skipped = [], []
    for scenic in scenics:
        gold_path = gold_map[scenic]
        if not Path(gold_path).exists():
            skipped.append({'scenic_id': scenic, 'reason': f'缺少金标 {Path(gold_path).name}'})
            print(f'[跳过] {scenic}: 未找到金标 {Path(gold_path).name}，本轮不评估该景区')
            continue
        results.append(evaluate(args.version, scenic, gold_path, args.outputs))

    if not results:
        print(f'\n本轮没有任何景区的金标准（需要 outputs/gold_<景区>.json）。'
              f'\n这不是错误：实验二的任务书只要求人工抽查，不强制准确率。'
              f'\n如需量化指标，请先按 docs 说明补标金标后重跑本脚本。')
        return 0

    texts = {r['doc_id']: r['clean_text'] for r in load_json(args.dataset)}
    totals = {'tp': 0, 'fp': 0, 'fn': 0}
    for result in results:
        for key in totals:
            totals[key] += result['overall'][key]
        for error in result['errors']['predicted_only'] + result['errors']['gold_only']:
            text = texts[error['doc_id']]
            positions = []
            start = text.find(error['text'])
            while start >= 0:
                end = start + len(error['text'])
                positions.append({'start': start, 'end': end,
                                  'context': text[max(0, start - 20):end + 20]})
                start = text.find(error['text'], end)
            error['occurrences_in_source'] = positions
    tp, fp, fn = totals['tp'], totals['fp'], totals['fn']
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    overall = {**totals, 'precision': round(precision, 4), 'recall': round(recall, 4),
               'f1': round(2 * precision * recall / (precision + recall), 4)
               if precision + recall else 0.0}
    payload = {
        'version': args.version, 'evaluation_level': 'document_type_surface_name',
        'limitations': ['同篇同类型同名实体去重，不是逐次出现位置的准确率。',
                        '只评价金标 doc_scope；词表与金标同源，不代表新数据泛化性能。',
                        '当前金标含用户授权合入的审计修订；原始复核记录已归档，变更见 gold_audit.json。'],
        'overall': overall, 'results': results, 'skipped': skipped}
    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8', newline='\n')
    write_json(args.outputs / f'evaluation_{args.version}.json', payload)
    write_json(args.outputs / 'evaluation.json', {
        'evaluation_level': 'document_type_surface_name',
        'versions': {v: f'evaluation_{v}.json' for v in VERSIONS
                     if (args.outputs / f'evaluation_{v}.json').exists()}})

    header = f"{'景区':<14}{'类型':<10}{'P':>8}{'R':>8}{'F1':>8}{'TP':>6}{'FP':>6}{'FN':>6}"
    print(header)
    print('-' * 60)
    for result in results:
        overall = result['overall']
        print(f"{result['scenic_id']:<14}{'总体':<10}{overall['precision']:>8.2f}{overall['recall']:>8.2f}"
              f"{overall['f1']:>8.2f}{overall['tp']:>6}{overall['fp']:>6}{overall['fn']:>6}")
        for entity_type in TYPES:
            m = result['by_type'][entity_type]
            print(f"{'':<14}{TYPE_CN[entity_type]:<10}{m['precision']:>8.2f}{m['recall']:>8.2f}"
                  f"{m['f1']:>8.2f}{m['tp']:>6}{m['fp']:>6}{m['fn']:>6}")
        print()
    if skipped:
        print('跳过:', ', '.join(s['scenic_id'] for s in skipped))
    return 0


if __name__ == '__main__':
    sys.exit(main())

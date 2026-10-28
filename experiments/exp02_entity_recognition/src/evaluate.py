#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实验二：按名称级金标评估 v1 / v2 的精确率、覆盖率与 F1。

用法（仓库根目录运行）：

    python experiments/exp02_entity_recognition/src/evaluate.py

读取 outputs/gold_huangshan.json 与 outputs/entities_{v1,v2}.json，
写出 outputs/evaluation.json，并在终端打印对照表。
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parent
OUTPUTS = SRC.parent / 'outputs'
TYPES = ('POI', 'TRANSPORT', 'TIME')
TYPE_CN = {'POI': '景点POI', 'TRANSPORT': '交通方式', 'TIME': '时间节点'}


def norm(text):
    return re.sub(r'\s+', '', text)


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


def evaluate(version, gold):
    entities = load_json(OUTPUTS / f'entities_{version}.json')
    pred = pred_set(entities)
    truth = gold_set(gold)
    result = {'version': version, 'mentions': len(entities), 'overall': prf(pred, truth), 'by_type': {}}
    for entity_type in TYPES:
        p = {x for x in pred if x[1] == entity_type}
        g = {x for x in truth if x[1] == entity_type}
        result['by_type'][entity_type] = prf(p, g)
        result['by_type'][entity_type]['false_positive'] = sorted(x[2] for x in p - g)
        result['by_type'][entity_type]['false_negative'] = sorted(x[2] for x in g - p)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='实验二：v1/v2 名称级评估')
    parser.add_argument('--gold', type=Path, default=OUTPUTS / 'gold_huangshan.json')
    args = parser.parse_args(argv)

    gold = load_json(args.gold)
    results = [evaluate('v1', gold), evaluate('v2', gold)]
    (OUTPUTS / 'evaluation.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

    header = f"{'版本':<6}{'类型':<10}{'P':>8}{'R':>8}{'F1':>8}{'TP':>6}{'FP':>6}{'FN':>6}"
    print(header)
    print('-' * len(header.encode('gbk', errors='ignore')))
    for result in results:
        overall = result['overall']
        print(f"{result['version']:<6}{'总体':<10}{overall['precision']:>8.2f}{overall['recall']:>8.2f}"
              f"{overall['f1']:>8.2f}{overall['tp']:>6}{overall['fp']:>6}{overall['fn']:>6}")
        for entity_type in TYPES:
            m = result['by_type'][entity_type]
            print(f"{'':<6}{TYPE_CN[entity_type]:<10}{m['precision']:>8.2f}{m['recall']:>8.2f}"
                  f"{m['f1']:>8.2f}{m['tp']:>6}{m['fp']:>6}{m['fn']:>6}")
        print()

    for result in results:
        print(f"[{result['version']}] 误识别样例:", '、'.join(
            f"{t}:{'/'.join(v['false_positive'][:8])}" for t, v in result['by_type'].items() if v['false_positive']))
        print(f"[{result['version']}] 漏识别样例:", '、'.join(
            f"{t}:{'/'.join(v['false_negative'][:8])}" for t, v in result['by_type'].items() if v['false_negative']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

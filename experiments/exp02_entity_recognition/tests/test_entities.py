#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实验二的最小回归测试：只校验结构，不依赖 matplotlib 绘图。

运行（仓库根目录）：

    python experiments/exp02_entity_recognition/tests/test_entities.py
    pytest experiments/exp02_entity_recognition/tests -q   # 也可

覆盖以下检查：
1. 位置口径   clean_text[start:end] == text
2. 无重复     (doc_id, start, end, entity_type) 唯一
3. 无重叠     同一文档内实体区间两两不相交
4. 三类实体计数、统计JSON和词频CSV与实体文件一致
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUTS = Path(__file__).resolve().parents[1] / 'outputs'
DATASET = ROOT / 'data/processed/full/selected_v2/dataset.json'

SCENICS = ('TAISHAN', 'WULINGYUAN', 'JINGYUETAN')
VERSIONS = ('v1', 'v2', 'v3', 'v4', 'v5')
TYPES = ('POI', 'TRANSPORT', 'TIME')


def load_texts():
    if not DATASET.exists():
        raise SystemExit(f'缺少数据集: {DATASET}')
    records = json.loads(DATASET.read_text(encoding='utf-8'))
    return {r['doc_id']: r['clean_text'] for r in records}


def load_entities(scenic, version):
    path = OUTPUTS / f'entities_{scenic}_{version}.json'
    if not path.exists():
        raise SystemExit(f'缺少实体文件: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def check_spans(entities, texts):
    for e in entities:
        assert texts[e['doc_id']][e['start']:e['end']] == e['text'], f'位置不一致: {e}'


def check_duplicates(entities):
    keys = {(e['doc_id'], e['start'], e['end'], e['entity_type']) for e in entities}
    assert len(keys) == len(entities), f'存在重复记录: {len(entities) - len(keys)} 条'


def check_overlaps(entities):
    spans = {}
    for e in entities:
        spans.setdefault(e['doc_id'], []).append((e['start'], e['end']))
    for doc_id, pairs in spans.items():
        pairs.sort()
        for (s1, e1), (s2, e2) in zip(pairs, pairs[1:]):
            assert e1 <= s2, f'{doc_id} 区间重叠: ({s1},{e1}) 与 ({s2},{e2})'


def check_stats(entities, scenic, version):
    stats = json.loads((OUTPUTS / f'stats_{scenic}_{version}.json').read_text(encoding='utf-8'))
    counts = Counter(e['entity_type'] for e in entities)
    assert counts == stats['by_type'] and stats['entity_mentions'] == len(entities), \
        f'{scenic} {version} 统计与实体数不一致'
    expected = Counter((e['entity_type'], e['text'], e['canonical']) for e in entities)
    with (OUTPUTS / f'entity_freq_{scenic}_{version}.csv').open(encoding='utf-8', newline='') as file:
        rows = list(csv.DictReader(file))
    actual = {(row['entity_type'], row['text'], row['canonical']): int(row['count']) for row in rows}
    assert len(rows) == len(actual) and actual == expected, f'{scenic} {version} 词频与实体不一致'
    assert stats['scenic_id'] == scenic, f'{scenic} {version} 的 scenic_id 写错'


def check_three_types(entities, scenic, version):
    seen = {e['entity_type'] for e in entities}
    assert seen == set(TYPES), f'{scenic} {version} 缺少实体类型: {set(TYPES) - seen}'


def main(argv=None):
    parser = argparse.ArgumentParser(description='校验实验二的结构化产物与词频')
    parser.add_argument('--version', nargs='+', choices=(*VERSIONS, 'v6', 'v7'), default=VERSIONS)
    versions = parser.parse_args(argv).version
    texts = load_texts()
    total = 0
    for version in versions:
        for scenic in SCENICS:
            entities = load_entities(scenic, version)
            check_spans(entities, texts)
            check_duplicates(entities)
            check_overlaps(entities)
            check_stats(entities, scenic, version)
            check_three_types(entities, scenic, version)
            total += len(entities)
    print(f'ok: {len(versions) * len(SCENICS)} 个文件、{total} 条实体，位置、重复、重叠、分类统计与词频校验通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())

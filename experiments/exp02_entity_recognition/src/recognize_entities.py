#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实验二：游览步骤的实体识别（selected_v2，三景区）。

v1 基线：jieba 默认分词 + 后缀规则 + 数字/关键词规则；不使用自定义词典与停用词。
v2 优化：common + 景区专名词表、停用词与片段拦截、四位时刻上下文校验、行程日与时刻正则。

用法（仓库根目录运行）：

    python experiments/exp02_entity_recognition/src/recognize_entities.py --version v1
    python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2
    python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2 --scenic TAISHAN

位置口径：start/end 为 clean_text 的 Python Unicode 字符索引，左闭右开，
满足 clean_text[start:end] == text。
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import jieba

ROOT = Path(__file__).resolve().parents[3]
SRC = Path(__file__).resolve().parent
CONFIG = SRC / 'config'
DEFAULT_INPUT = ROOT / 'data/processed/full/selected_v2/dataset.json'

SCENICS = ('TAISHAN', 'WULINGYUAN', 'JINGYUETAN')
SCENIC_CN = {'TAISHAN': '泰山', 'WULINGYUAN': '张家界武陵源', 'JINGYUETAN': '净月潭'}

TYPE_ORDER = {'POI': 0, 'TRANSPORT': 1, 'TIME': 2}
TYPE_CN = {'POI': '景点POI', 'TRANSPORT': '交通方式', 'TIME': '时间节点'}
GROUP_OF = {'POI': 'poi', 'TRANSPORT': 'transport', 'TIME': 'time'}

# ---- v1：只靠词形后缀与闭类词，不含领域词表 ----
V1_POI_SUFFIX = ('峰', '顶', '寺', '庙', '亭', '楼', '阁', '门', '宫', '殿', '园', '桥',
                 '溪', '谷', '洞', '潭', '瀑', '岭', '台', '湾', '湖', '崖', '坊', '堂', '寨')
V1_TRANSPORT_SUFFIX = ('索道', '缆车', '天梯', '竹筏')
V1_TRANSPORT_WORDS = {'大巴', '大巴车', '环保车', '观光车', '火车', '高铁', '自驾', '徒步',
                      '步行', '地铁', '公交', '公交车', '出租车', '游船', '小火车', '观光小火车'}
V1_TIME_WORDS = {'凌晨', '早上', '上午', '中午', '下午', '傍晚', '晚上', '夜里',
                 '日出', '日落', '次日', '第二天', '当天', '半天', '一日', '两天'}
V1_NUMBER = re.compile(r'\d{3,4}')

# ---- v2 追加 ----
# v2 只保留高精度后缀做未登录词兜底：这些字结尾的 3 字以上词，几乎都是景区地名；
# 峰/顶/门/园/台 等宽后缀在 v1 里产生了大量“登顶”“主峰”“大门”噪声，v2 不再使用。
V2_POI_SUFFIX = ('峰', '寺', '庙', '洞', '瀑', '潭', '阁', '祠', '坊', '寨', '峪')
V2_T_PLUS = re.compile(r'T\s*\+\s*1')
V2_CLOCK = re.compile(r'\d{1,2}\s*[:：]\s*\d{2}')
V2_POINT = re.compile(r'\d{1,2}\s*点(?:\d{1,2}\s*分)?')
HAS_CJK = re.compile(r'[\u4e00-\u9fff]')


def is_noise_token(token):
    if not token or not token.strip():
        return True
    for ch in token:
        if unicodedata.category(ch)[0] not in {'P', 'Z', 'S', 'C'}:
            return False
    return True


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_records(path, scenic_id):
    records = load_json(path)
    return [r for r in records if r['scenic_id'] == scenic_id]


def norm_entry(value):
    return {'subtype': value} if isinstance(value, str) else dict(value)


def build_lexicon(lexicon, scenic):
    groups = {'poi': {}, 'transport': {}, 'time': {}}
    common = lexicon.get('common', {})
    for group in ('poi', 'transport', 'time'):
        for word, value in common.get(group, {}).items():
            groups[group][word] = norm_entry(value)
    scenic_block = lexicon['scenics'].get(scenic, {})
    for group in ('poi', 'transport', 'time'):
        for word, value in scenic_block.get(group, {}).items():
            groups[group][word] = norm_entry(value)
    return groups


def build_stopwords(stop, scenic):
    return {
        'suffix_noise': set(stop.get('suffix_noise', [])),
        'generic_place': set(stop.get('generic_place', {}).get(scenic, [])),
        'off_scenic': set(stop.get('off_scenic', [])),
    }


def split_sentences(text):
    marks = '。！？；!?;\n'
    out, start = [], 0
    for i, ch in enumerate(text):
        if ch in marks:
            seg = text[start:i + 1]
            if seg.strip():
                out.append({'sid': len(out) + 1, 'start': start, 'end': i + 1, 'text': seg})
            start = i + 1
    if start < len(text):
        seg = text[start:]
        if seg.strip():
            out.append({'sid': len(out) + 1, 'start': start, 'end': len(text), 'text': seg})
    return out


def sentence_of(sentences, pos):
    for sent in sentences:
        if sent['start'] <= pos < sent['end']:
            return sent['sid']
    return sentences[-1]['sid'] if sentences else 0


def tokenize(text):
    return [(w, s, e) for w, s, e in jieba.tokenize(text) if not is_noise_token(w)]


def register_lexicon(groups):
    for group in ('poi', 'transport', 'time'):
        for word in groups[group]:
            jieba.add_word(word, freq=20000)


def detect_v1(token):
    if token in V1_TIME_WORDS:
        return 'TIME', 'period', 'keyword'
    if V1_NUMBER.fullmatch(token):
        return 'TIME', 'clock', 'number'
    if token in V1_TRANSPORT_WORDS:
        return 'TRANSPORT', 'mode', 'keyword'
    if len(token) >= 2 and token.endswith(V1_TRANSPORT_SUFFIX):
        return 'TRANSPORT', 'cableway', 'suffix'
    if len(token) >= 2 and token.endswith(V1_POI_SUFFIX):
        return 'POI', 'suffix', 'suffix'
    return None


def detect_v2(token, text, end, groups, stop):
    for entity_type, group in (('POI', 'poi'), ('TRANSPORT', 'transport'), ('TIME', 'time')):
        entry = groups[group].get(token)
        if entry:
            return entity_type, entry.get('subtype', 'other'), 'lexicon'

    if token in V1_TIME_WORDS:
        return 'TIME', 'period', 'keyword'

    if token in stop['suffix_noise'] or token in stop['generic_place'] or token in stop['off_scenic']:
        return None

    # 未登录词兜底：仅 3 字以上、且为高精度地名后缀
    if 3 <= len(token) and token.endswith(V2_POI_SUFFIX) and HAS_CJK.search(token):
        return 'POI', 'suffix', 'suffix'
    if 3 <= len(token) and token.endswith(V1_TRANSPORT_SUFFIX):
        return 'TRANSPORT', 'cableway', 'suffix'
    return None


def resolve_overlaps(cands):
    ordered = sorted(cands, key=lambda c: (-(c['end'] - c['start']),
                                            TYPE_ORDER[c['entity_type']], c['start']))
    kept = []
    for cand in ordered:
        if any(not (cand['end'] <= k['start'] or cand['start'] >= k['end']) for k in kept):
            continue
        kept.append(cand)
    return sorted(kept, key=lambda c: (c['start'], c['end']))


def decorate(entity, groups):
    entry = groups[GROUP_OF[entity['entity_type']]].get(entity['text'], {})
    in_lexicon = bool(entry)
    if entity['method'] == 'suffix' and not in_lexicon:
        granularity = 'unknown'
    else:
        granularity = entry.get('granularity', 'specific')
    record = dict(entity)
    record['granularity'] = granularity
    record['canonical'] = entry.get('canonical', entity['text'])
    return record


def extract(records, version, groups, stop, scenic):
    all_entities, per_doc = [], {}
    for record in records:
        text = record['clean_text']
        sentences = split_sentences(text)
        cands = []
        for token, start, end in tokenize(text):
            if version == 'v1':
                hit = detect_v1(token)
            else:
                hit = detect_v2(token, text, end, groups, stop)
            if not hit:
                continue
            entity_type, subtype, method = hit
            cands.append({
                'doc_id': record['doc_id'],
                'scenic_id': scenic,
                'text': token,
                'entity_type': entity_type,
                'subtype': subtype,
                'start': start,
                'end': end,
                'sentence_id': sentence_of(sentences, start),
                'method': method,
            })

        if version == 'v2':
            for pattern, subtype, method in ((V2_CLOCK, 'clock', 'regex_clock'),
                                             (V2_POINT, 'period', 'regex_point'),
                                             (V2_T_PLUS, 'day', 'regex_day')):
                for m in pattern.finditer(text):
                    if any(not (m.end() <= c['start'] or m.start() >= c['end']) for c in cands):
                        continue
                    cands.append({
                        'doc_id': record['doc_id'],
                        'scenic_id': scenic,
                        'text': m.group(),
                        'entity_type': 'TIME',
                        'subtype': subtype,
                        'start': m.start(),
                        'end': m.end(),
                        'sentence_id': sentence_of(sentences, m.start()),
                        'method': method,
                    })

        entities = resolve_overlaps(cands)
        entities = [decorate(ent, groups) for ent in entities]
        for ent in entities:
            assert text[ent['start']:ent['end']] == ent['text'], f"位置与原文不一致: {ent}"
        per_doc[record['doc_id']] = {
            'chars': len(text),
            'sentences': len(sentences),
            'entities': len(entities),
            'by_type': dict(Counter(e['entity_type'] for e in entities)),
        }
        all_entities.extend(entities)
    return all_entities, per_doc


def summarize(entities, per_doc, version, scenic):
    by_type = Counter(e['entity_type'] for e in entities)
    unique = defaultdict(set)
    by_canonical = defaultdict(Counter)
    for ent in entities:
        unique[ent['entity_type']].add(ent['text'])
        by_canonical[ent['entity_type']][ent['canonical']] += 1
    return {
        'version': version,
        'scenic_id': scenic,
        'scenic_name': SCENIC_CN.get(scenic, scenic),
        'doc_count': len(per_doc),
        'chars': sum(v['chars'] for v in per_doc.values()),
        'entity_mentions': len(entities),
        'by_type': {t: by_type.get(t, 0) for t in ('POI', 'TRANSPORT', 'TIME')},
        'unique_names': {t: len(unique[t]) for t in ('POI', 'TRANSPORT', 'TIME')},
        'by_canonical': {t: dict(sorted(by_canonical[t].items(), key=lambda kv: (-kv[1], kv[0])))
                         for t in ('POI', 'TRANSPORT', 'TIME')},
        'granularity': dict(Counter(e['granularity'] for e in entities)),
        'per_doc': per_doc,
    }


def write_frequency(entities, out_dir, version, scenic):
    counter = Counter((e['entity_type'], e['text'], e['canonical']) for e in entities)
    rows = [{'entity_type': t, 'text': w, 'canonical': c, 'count': n}
            for (t, w, c), n in sorted(counter.items(),
                                       key=lambda kv: (TYPE_ORDER[kv[0][0]], kv[0][2], -kv[1], kv[0][1]))]
    path = out_dir / f'entity_freq_{scenic}_{version}.csv'
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['entity_type', 'text', 'canonical', 'count'],
                                lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return rows


def plot_frequency(rows, out_dir, version, scenic):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.ticker import MaxNLocator

    font_path = Path(r'C:\Windows\Fonts\msyh.ttc')
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        name = font_manager.FontProperties(fname=str(font_path)).get_name()
    else:
        name = 'SimHei'
    plt.rcParams['font.sans-serif'] = [name, 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    colors = {'POI': '#3a6ea5', 'TRANSPORT': '#c9752c', 'TIME': '#5a8a5a'}
    fig, axes = plt.subplots(3, 1, figsize=(9, 10.5), dpi=150)
    for ax, entity_type in zip(axes, ('POI', 'TRANSPORT', 'TIME')):
        subset = sorted((r for r in rows if r['entity_type'] == entity_type),
                        key=lambda r: (-r['count'], r['text']))[:10]
        subset.reverse()
        labels = [r['text'] for r in subset]
        values = [r['count'] for r in subset]
        ax.barh(labels, values, color=colors[entity_type], height=0.62)
        for i, v in enumerate(values):
            ax.text(v + 0.08, i, str(v), va='center', fontsize=9)
        ax.set_title(f'{TYPE_CN[entity_type]} 词频 Top10（{version}）', fontsize=12, pad=8)
        ax.set_xlabel('出现次数')
        ax.set_xlim(0, max(values) + 1.2 if values else 1)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(axis='x', linestyle=':', alpha=0.45)
        ax.set_axisbelow(True)
        for spine in ('top', 'right'):
            ax.spines[spine].set_visible(False)
    fig.suptitle(f'{SCENIC_CN.get(scenic, scenic)} 实体词频统计（{version}，按原文表面形式）', fontsize=14)
    fig.text(0.5, 0.005,
             '注：具名线路不与泛称合并（如“天子山索道”单列，“索道”只计泛称）；'
             f'类别汇总见 stats_{scenic}_{version}.json 的 by_canonical',
             ha='center', fontsize=8, color='#666666')
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    path = out_dir / f'entity_freq_{scenic}_{version}.png'
    fig.savefig(path)
    plt.close(fig)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description='实验二：景区实体识别（selected_v2）')
    parser.add_argument('--version', choices=['v1', 'v2'], default='v2')
    parser.add_argument('--scenic', nargs='*', default=['all'],
                        help='景区编号，多个用空格分隔；all 表示三个景区')
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--outputs', type=Path, default=SRC.parent / 'outputs')
    args = parser.parse_args(argv)

    lexicon = load_json(CONFIG / 'lexicon.json')
    stop_raw = load_json(CONFIG / 'stopwords.json')
    scenics = list(SCENICS) if args.scenic == ['all'] else args.scenic
    unknown = [s for s in scenics if s not in SCENICS]
    if unknown:
        raise SystemExit(f'未知景区编号: {unknown}，可选 {SCENICS}')

    args.outputs.mkdir(parents=True, exist_ok=True)
    summary = {}
    for scenic in scenics:
        groups = build_lexicon(lexicon, scenic)
        stop = build_stopwords(stop_raw, scenic)
        if args.version == 'v2':
            register_lexicon(groups)

        records = load_records(args.input, scenic)
        if not records:
            raise SystemExit(f'未找到景区 {scenic} 的记录: {args.input}')

        entities, per_doc = extract(records, args.version, groups, stop, scenic)
        stats = summarize(entities, per_doc, args.version, scenic)

        (args.outputs / f'entities_{scenic}_{args.version}.json').write_text(
            json.dumps(entities, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        (args.outputs / f'stats_{scenic}_{args.version}.json').write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

        rows = write_frequency(entities, args.outputs, args.version, scenic)
        png = plot_frequency(rows, args.outputs, args.version, scenic)
        summary[scenic] = {
            'name': SCENIC_CN.get(scenic, scenic),
            'docs': stats['doc_count'],
            'chars': stats['chars'],
            'mentions': stats['entity_mentions'],
            'by_type': stats['by_type'],
            'unique': stats['unique_names'],
            'chart': png.name,
        }
        print(json.dumps(summary[scenic], ensure_ascii=False))

    aggregate = {
        'version': args.version,
        'scenics': summary,
        'totals': {
            'docs': sum(v['docs'] for v in summary.values()),
            'chars': sum(v['chars'] for v in summary.values()),
            'mentions': sum(v['mentions'] for v in summary.values()),
            'by_type': {t: sum(v['by_type'][t] for v in summary.values())
                        for t in ('POI', 'TRANSPORT', 'TIME')},
        },
    }
    (args.outputs / f'stats_all_{args.version}.json').write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(aggregate['totals'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

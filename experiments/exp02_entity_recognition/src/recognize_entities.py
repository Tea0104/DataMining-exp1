#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实验二：游览步骤的实体识别（黄山单景区，v1 基线 / v2 优化）。

v1 基线：jieba 默认分词 + 后缀规则 + 数字/关键词规则；不使用自定义词典与停用词。
v2 优化：加载自定义词典（config/lexicon.json）与停用词（config/stopwords.json），
         细化数字时刻规则，并补充“T + 1”这类行程日表达。

用法（仓库根目录运行）：

    python experiments/exp02_entity_recognition/src/recognize_entities.py --version v1
    python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2

位置口径：所有 start/end 都是 clean_text 的 Python Unicode 字符索引，左闭右开，
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

TYPE_ORDER = {'POI': 0, 'TRANSPORT': 1, 'TIME': 2}
TYPE_CN = {'POI': '景点POI', 'TRANSPORT': '交通方式', 'TIME': '时间节点'}
GROUP_OF = {'POI': 'poi', 'TRANSPORT': 'transport', 'TIME': 'time'}

# ---- v1 规则：只靠词形后缀与通用闭类词，不含领域词表 ----
V1_POI_SUFFIX = ('峰', '寺', '亭', '楼', '宾馆', '景区', '顶', '海', '台', '谷', '门', '园')
V1_TRANSPORT_SUFFIX = ('索道', '缆车')
V1_TRANSPORT_WORDS = {'大巴', '面包车', '火车', '高铁', '自驾', '徒步', '步行', '地铁', '公交', '飞机'}
V1_TIME_WORDS = {'早上', '上午', '中午', '下午', '傍晚', '晚上', '夜里', '凌晨',
                 '日出', '日落', '当晚', '第二天', '两天', '一日'}
V1_NUMBER = re.compile(r'\d{3,4}')

# ---- v2 追加规则 ----
V2_POI_SUFFIX = V1_POI_SUFFIX + ('山庄', '饭店', '度假区')
V2_NUMBER = re.compile(r'\d{4}')
V2_T_PLUS = re.compile(r'T\s*\+\s*1')
HAS_CJK = re.compile(r'[\u4e00-\u9fff]')


def is_noise_token(token):
    """空白、标点、符号、emoji 一律不作为实体候选。"""
    if not token or not token.strip():
        return True
    for ch in token:
        cat = unicodedata.category(ch)
        if cat[0] not in {'P', 'Z', 'S', 'C'}:
            return False
    return True


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_records(path, scenic_id):
    records = load_json(path)
    return [r for r in records if r['scenic_id'] == scenic_id]


def split_sentences(text):
    """按句末标点与换行切句，保留绝对偏移。"""
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


def register_lexicon(lexicon):
    """v2：把词表写入 jieba 自定义词典，保证长实体不被切碎。"""
    for group in ('poi', 'transport', 'time'):
        for word in lexicon[group]:
            jieba.add_word(word, freq=20000)


def detect_v1(token):
    """v1：纯词形规则，返回 (entity_type, subtype, method) 或 None。"""
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


def detect_v2(token, text, end, lexicon, stop, reject_ctx):
    """v2：词表优先，其次后缀规则，并加停用词与数字上下文约束。"""
    for entity_type, group in (('POI', 'poi'), ('TRANSPORT', 'transport'), ('TIME', 'time')):
        if token in lexicon[group]:
            return entity_type, lexicon[group][token]['subtype'], 'lexicon'

    if token in V1_TIME_WORDS:
        return 'TIME', 'period', 'keyword'
    if V2_NUMBER.fullmatch(token):
        tail = text[end:end + 8]
        if not any(ctx in tail for ctx in reject_ctx):
            return 'TIME', 'clock', 'number'

    if token in stop['suffix_noise'] or token in stop['generic_place'] or token in stop['off_scenic']:
        return None

    if len(token) >= 2 and token.endswith(V1_TRANSPORT_SUFFIX):
        return 'TRANSPORT', 'cableway', 'suffix'
    if len(token) >= 2 and token.endswith(V2_POI_SUFFIX) and HAS_CJK.search(token):
        return 'POI', 'suffix', 'suffix'
    return None


def resolve_overlaps(cands):
    """长实体优先，同跨度按 POI > TRANSPORT > TIME 取一个。"""
    ordered = sorted(cands, key=lambda c: (-(c['end'] - c['start']),
                                            TYPE_ORDER[c['entity_type']], c['start']))
    kept = []
    for cand in ordered:
        if any(not (cand['end'] <= k['start'] or cand['start'] >= k['end']) for k in kept):
            continue
        kept.append(cand)
    return sorted(kept, key=lambda c: (c['start'], c['end']))


def decorate(entity, lexicon):
    """补粒度元数据：canonical 上位类别 + granularity 层级。

    只加字段，不改 text / start / end。canonical 仅用于统计与 Schema 分层，
    不能当作实体 ID——云谷索道与玉屏索道的 canonical 同为“索道”，
    一旦拿它作节点 ID，上山与下山两条索道就会被错误合并。
    """
    group = GROUP_OF[entity['entity_type']]
    entry = lexicon[group].get(entity['text'], {})
    in_lexicon = bool(entry)
    if entity['method'] == 'suffix' and not in_lexicon:
        granularity = 'unknown'
    else:
        granularity = entry.get('granularity', 'specific')
    record = dict(entity)
    record['granularity'] = granularity
    record['canonical'] = entry.get('canonical', entity['text'])
    return record


def extract(records, version, lexicon, stop):
    reject_ctx = stop['time_number_reject_context']
    all_entities, per_doc = [], {}
    for record in records:
        text = record['clean_text']
        sentences = split_sentences(text)
        cands = []
        for token, start, end in tokenize(text):
            if version == 'v1':
                hit = detect_v1(token)
            else:
                hit = detect_v2(token, text, end, lexicon, stop, reject_ctx)
            if not hit:
                continue
            entity_type, subtype, method = hit
            cands.append({
                'doc_id': record['doc_id'],
                'scenic_id': record['scenic_id'],
                'text': token,
                'entity_type': entity_type,
                'subtype': subtype,
                'start': start,
                'end': end,
                'sentence_id': sentence_of(sentences, start),
                'method': method,
            })

        # v2 追加“T + 1”这类跨 token 的行程日表达
        if version == 'v2':
            for m in V2_T_PLUS.finditer(text):
                if any(not (m.end() <= c['start'] or m.start() >= c['end']) for c in cands):
                    continue
                cands.append({
                    'doc_id': record['doc_id'],
                    'scenic_id': record['scenic_id'],
                    'text': m.group(),
                    'entity_type': 'TIME',
                    'subtype': 'day',
                    'start': m.start(),
                    'end': m.end(),
                    'sentence_id': sentence_of(sentences, m.start()),
                    'method': 'regex_day',
                })

        entities = resolve_overlaps(cands)
        entities = [decorate(ent, lexicon) for ent in entities]
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


def summarize(entities, per_doc, version):
    by_type = Counter(e['entity_type'] for e in entities)
    unique = defaultdict(set)
    by_canonical = defaultdict(Counter)
    for ent in entities:
        unique[ent['entity_type']].add(ent['text'])
        by_canonical[ent['entity_type']][ent['canonical']] += 1
    return {
        'version': version,
        'scenic_id': 'huangshan',
        'doc_count': len(per_doc),
        'entity_mentions': len(entities),
        'by_type': {t: by_type.get(t, 0) for t in ('POI', 'TRANSPORT', 'TIME')},
        'unique_names': {t: len(unique[t]) for t in ('POI', 'TRANSPORT', 'TIME')},
        'by_canonical': {t: dict(sorted(by_canonical[t].items(), key=lambda kv: (-kv[1], kv[0])))
                         for t in ('POI', 'TRANSPORT', 'TIME')},
        'granularity': dict(Counter(e['granularity'] for e in entities)),
        'per_doc': per_doc,
    }


def write_frequency(entities, out_dir, version):
    counter = Counter((e['entity_type'], e['text'], e['canonical']) for e in entities)
    rows = [{'entity_type': t, 'text': w, 'canonical': c, 'count': n}
            for (t, w, c), n in sorted(counter.items(),
                                       key=lambda kv: (TYPE_ORDER[kv[0][0]], kv[0][2], -kv[1], kv[0][1]))]
    path = out_dir / f'entity_freq_{version}.csv'
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['entity_type', 'text', 'canonical', 'count'],
                                lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return rows


def plot_frequency(rows, out_dir, version):
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
    fig.suptitle(f'黄山景区实体词频统计（{version}，按原文表面形式）', fontsize=14)
    fig.text(0.5, 0.005,
             '注：同名具名实体不与泛称合并，例如“云谷索道/玉屏索道”单列、“索道”仅计泛称；'
             f'类别级汇总见 stats_{version}.json 的 by_canonical',
             ha='center', fontsize=8, color='#666666')
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    path = out_dir / f'entity_freq_{version}.png'
    fig.savefig(path)
    plt.close(fig)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description='实验二：黄山景区实体识别')
    parser.add_argument('--version', choices=['v1', 'v2'], default='v1')
    parser.add_argument('--scenic', default='huangshan')
    parser.add_argument('--input', type=Path, default=ROOT / 'data/processed/sample_v1.json')
    parser.add_argument('--outputs', type=Path, default=SRC.parent / 'outputs')
    args = parser.parse_args(argv)

    lexicon = load_json(CONFIG / 'lexicon.json')
    stop = load_json(CONFIG / 'stopwords.json')
    if args.version == 'v2':
        register_lexicon(lexicon)

    records = load_records(args.input, args.scenic)
    if not records:
        raise SystemExit(f'未找到景区 {args.scenic} 的记录: {args.input}')

    entities, per_doc = extract(records, args.version, lexicon, stop)
    stats = summarize(entities, per_doc, args.version)

    args.outputs.mkdir(parents=True, exist_ok=True)
    (args.outputs / f'entities_{args.version}.json').write_text(
        json.dumps(entities, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    (args.outputs / f'stats_{args.version}.json').write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

    rows = write_frequency(entities, args.outputs, args.version)
    png = plot_frequency(rows, args.outputs, args.version)

    print(json.dumps({
        'version': args.version,
        'docs': stats['doc_count'],
        'mentions': stats['entity_mentions'],
        'by_type': stats['by_type'],
        'unique_names': stats['unique_names'],
        'granularity': stats['granularity'],
        'chart': str(png),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())

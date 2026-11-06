"""用通用的 POI 类别及边界规则整理独立 LLM 候选。"""
import argparse
from pathlib import Path
import re

from run import DATASET, REFERENCE, gold_set, nonoverlap, pred_set, prf, read, sha, write


GENERIC = set("""
入口 出口 公园入口 景区入口 主入口 登山口
停车场 服务中心 游客中心 检票处 检票口 换乘站 乘车点 起点站 终点站
观景台 观景点 平台 山顶 山峰 山谷 公路 步道 栈道 木栈道 徒步栈道 步行栈道
码头 吊桥 大坝 水塔 荷花池 芦苇荡 古槐
山门 大殿 正殿 配殿 东配殿 西配殿 戏台 照壁 摩崖
""".split())
TRANSPORT = re.compile(r'(?:索道(?:[A-ZＡ-Ｚ]线|[上下]?站|[上下]端点?|乘车点)?|缆车|电梯|地铁|换乘站|乘车点)$')
ENTRANCE = re.compile(r'(.{2,}?)(?:景区)?(?:登山(?:入口|起点|口)|(?<!出)入口|出口)$')
DIRECTIONAL_ENTRANCE = re.compile(r'[东南西北正侧](?:入口|出口)$')
GATE_PAIR = re.compile(r'(景区[正东南西北]门)(.{2,}(?:广场|游客中心|集散中心))$')
HOTEL_BRANCH = re.compile(r'(.{2,}(?:酒店|宾馆|客栈))(?:[（(].+店[）)]|[*·\-—].+店)$')
PARK_SUFFIX = re.compile(r'(?:国家级风景名胜区|国家森林公园|风景名胜区|风景区|核心景区|景区|公园)$')
STATION_LABEL = re.compile(r'(.{2,})站点$')
INSCRIPTION_LABEL = re.compile(r'石刻(.+摩崖)$')
BUS_NUMBER = re.compile(r'[A-Z]*\d+公交站')
ROUTE_SIDE = re.compile(r'[前后东西南北][山坡](?=[）)。，、：；\s]|[上下]山|[上下]的|精华|$)')
ROUTE_APPROACH = re.compile(r'(?:游览|到达|经由|经过|走到|转往|进入|从|经|由|自)$')
ROUTE_ASCENT = re.compile(r'[）)]?(?:[上下]山|[上下](?=[，、。；]|的|$))')
ROUTE_DELIMITERS = '（(，,。、：:；;→ \t\n'


def is_transport(name, text):
    if TRANSPORT.search(name) or BUS_NUMBER.fullmatch(name):
        return True
    if not name.endswith('天梯'):
        return False
    literal = re.escape(name)
    return bool(re.search(
        r'(?:乘坐|坐|搭乘|搭)(?:过|了|上|[几一两三][遍次])*' + literal
        + '|' + literal + r'[^。！？\n]{0,35}垂直[^。！？\n]{0,12}电梯', text))


def boundary_parts(name):
    """返回原名称内仍独立成立的子串位置。"""
    pair = GATE_PAIR.fullmatch(name)
    if pair:
        return [pair.span(1), pair.span(2)]
    for pattern in (HOTEL_BRANCH, ENTRANCE, STATION_LABEL, INSCRIPTION_LABEL):
        if pattern == ENTRANCE and DIRECTIONAL_ENTRANCE.search(name):
            continue
        match = pattern.fullmatch(name)
        if match:
            return [match.span(1)]
    return [(0, len(name))]


def refine(record, candidates):
    scenic = record['scenic_name']
    root = PARK_SUFFIX.sub('', scenic)
    text = record['clean_text']
    kept, changes = [], []
    for entity in candidates:
        name = entity['text']
        start, end = entity['start'], entity['end']
        if not 0 <= start < end <= len(text) or text[start:end] != name:
            raise ValueError(f"实体位置不匹配：{record['doc_id']}")
        if name in GENERIC or is_transport(name, text):
            parts = []
        else:
            parts = [(left, right) for left, right in boundary_parts(name)
                     if name[left:right] not in GENERIC
                     and not (PARK_SUFFIX.sub('', name[left:right]) == root and name[left:right] != root)]
        if parts != [(0, len(name))]:
            changes.append({'before': name, 'start': start, 'after': [name[l:r] for l, r in parts]})
        for left, right in parts:
            if (left, right) == (0, len(name)):
                kept.append(entity)
            else:
                kept.append({**entity, 'text': name[left:right], 'start': start + left,
                             'end': start + right, 'method': 'llm_boundary_refined'})
    occupied = nonoverlap(kept)
    route_nodes = []
    for match in ROUTE_SIDE.finditer(text):
        start, end = match.span()
        at_boundary = start == 0 or text[start - 1] in ROUTE_DELIMITERS
        if (ROUTE_APPROACH.search(text[max(0, start - 8):start])
                or at_boundary and ROUTE_ASCENT.match(text, end)):
            route_nodes.append({
                'doc_id': record['doc_id'], 'scenic_id': record['scenic_id'], 'entity_type': 'POI',
                'text': match[0], 'start': start, 'end': end, 'method': 'llm_route_context',
            })
    entities = nonoverlap(route_nodes, occupied)
    changes.extend({'before': None, 'start': e['start'], 'after': [e['text']]}
                   for e in entities if e.get('method') == 'llm_route_context' and e not in occupied)
    return entities, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = read(args.run / 'manifest.json')
    source = args.run / 'llm_entities.json'
    ids = set(manifest['documents'])
    records = {r['doc_id']: r for r in read(args.input) if r['doc_id'] in ids}
    if set(records) != ids:
        parser.error('找不到完整的抽取文档')
    input_hash = sha(args.input.read_bytes())
    if manifest.get('input_sha256', input_hash) != input_hash:
        parser.error('输入与抽取的原文版本不一致')
    groups = {doc_id: [] for doc_id in ids}
    for e in read(source):
        groups[e['doc_id']].append(e)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    entities, changes = [], {}
    for doc_id in sorted(ids):
        retained, audit = refine(records[doc_id], groups[doc_id])
        entities.extend(retained)
        if audit:
            changes[doc_id] = audit
    reference_hash = manifest.get('reference_sha256')
    if reference_hash and reference_hash != sha(REFERENCE.read_bytes()):
        parser.error('参考标注版本不一致')
    write(out / 'llm_entities.json', entities)
    write(out / 'boundary_audit.json', changes)
    write(out / 'manifest.json', {
        'documents': sorted(ids), 'input_sha256': input_hash,
        'source_entities_sha256': sha(source.read_bytes()), 'reference_sha256': reference_hash,
        'runner_sha256': sha(Path(__file__).read_bytes()),
    })
    if reference_hash:
        truth = {x for x in gold_set(read(REFERENCE)) if x[0] in ids and x[1] == 'POI'}
        pred = pred_set(entities)
        score = prf(pred, truth)
        write(out / 'evaluation.json', {
            'documents': sorted(ids), 'evaluation_level': 'document_type_surface_name',
            'scores': {'llm_boundary_refined': {
                **score, 'missed': sorted(truth - pred), 'unmatched_predictions': sorted(pred - truth),
            }},
        })
        print(score, flush=True)


if __name__ == '__main__':
    main()

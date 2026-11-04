"""以名称边界、命名语境和结构化行程补充 v3 的景点候选。"""
import re
from collections import Counter, defaultdict

import recognize_entities as base
import recognize_v3 as v3
import recognize_v4 as v4


CJK = r'[\u4e00-\u9fff·]'
HEADS = set(v4.PLACE_HEADS) | set('顶 榭 渡 川 池 洲 盘 槐 廊 棚 会馆 石刻 石碑 摩崖 牌坊 雪道 夜市 城区 街道'.split())
HEAD = '|'.join(sorted(HEADS, key=lambda value: (-len(value), value)))
NAMED = rf'{CJK}{{1,15}}?(?:{HEAD})'
NAME = re.compile(rf'{CJK}{{2,18}}')
PLACE = re.compile(rf'{NAMED}$')
GATE = re.compile(r'[东南西北]门')
EXTEND = re.compile(r'^(?:小广场|观景台|纪念馆|纪念碑|石坊|牌坊|石刻|石碑|游客中心|雪道)')
STONE_EXTEND = re.compile(r'^[刻碑]')
ALIAS_CUE = re.compile(r'旧称|古称|旧名|古名|又称|俗称|又名|改名为|更名为|改称|后改为')
ALIAS_ITEM = re.compile(rf'\s*(?:[“「『"](?P<quoted>{CJK}{{2,16}})[”」』"]|(?P<plain>{CJK}{{2,16}})(?=[、，。；！？\s]|$))')
ALIAS_CONTEXT = re.compile(rf'(?:{HEAD})[，。；、\s]?$')
HERITAGE = re.compile(rf'(?:题刻|石碑|石坊(?:为)?|匾额(?:写着)?|上刻(?:有)?|额书|石刻(?:上写着)?)[“」「"《](?P<name>{CJK}{{2,16}})[”「」"》]')
DESTINATION = re.compile(
    rf'(?:走到了?|抵达|途经|穿过|前往|经过|(?:就|再|才|可|回)到|看到的是|'
    rf'(?:前面|西北|东北|旁边|对面)(?:是|有)|山坡上有|终点站(?:为|是)?|'
    rf'由|宿|逛逛)(?P<name>{NAMED})(?=$|[，。；、\n）(（]|附近|的车|下车|里面|里有|一带|之间|进出|拍照|打卡)'
)
INTRO = re.compile(rf'(?:^|[。！？；，\n])\s*(?P<name>{NAMED})(?=，?(?:景点之一|始建于|修建于|坐落[在于]|位于|是[^，。]{{1,15}}(?:建筑|景点)))')
GATE_CONTEXT = re.compile(r'(?:(?:从|到|去|宿|走|回到)(?P<left>[东南西北]门)(?=进|出|的车|进入|[，。；、\n])|(?P<right>[东南西北]门)(?=进出|出园|入园))')
FIELD = re.compile(r'(?:^|[。；\n])\s*(?:住宿建议|午餐地点建议|途经景点|游览景点|(?:[\u4e00-\u9fff]{1,8})?景点)\s*[:：]\s*([^。；\n]+)')
TIMED = re.compile(r'^\s*(?:\d{1,2}[:：]\d{2}|\d{1,2}点(?:\d{1,2}分|半)?)\s+')
ROUTE = re.compile(r'→|——+|--+|—')
HEADING_PAIR = re.compile(rf'^(?P<primary>{NAMED})\s*[（(](?P<alias>{CJK}{{2,16}})[）)]$')
PHRASE = re.compile(
    r'乘车|乘船|乘坐|打车|出发|休整|入住|走到|下车|上山|下山|进山|来到|前往|'
    r'就像|就是|景区出入口|门票|可以|应该|需要|比如|古称|旧称|又称|合理规划|距离|'
    r'^(?:首先|晚上|早上|门口|公路|房间|当地|热门|著名|独立|人工|现场|自然|附近|'
    r'一处|第[一二三四五六七八九十]|原为|回望|爬|走出|左侧|右侧|最高处|线路是|路线是|'
    r'这样|那样|此路线|需|达(?=.{2,}))'
)
GENERIC = v3.GENERIC | v4.UNNAMED | {
    '景区出入口', '公园入口', '检票口', '山涧', '主入口', '美食街', '自驾游', '全天', '小吃街', '网红打卡点'
}


def named_span(raw, offset, *, trim_route=False):
    """从行程槽位保留原文名称的精确区间。"""
    label = re.match(r'\s*(?:第[一二三四五六七八九十\d]+站[:：]\s*|(?:徒步至|终点|起点|从|经|宿)\s*)?', raw)
    start = label.end()
    name = re.split(r'[（(【*]|\s+宿|\s+(?=[\u4e00-\u9fff])', raw[start:], maxsplit=1)[0].strip()
    name = name.strip('“”「」"《》 ').strip()
    if trim_route:
        name = name.removesuffix('站点')
    if NAME.fullmatch(name):
        start = raw.find(name, start)
        return offset + start, offset + start + len(name)
    return None


def aliases(text, known):
    for cue in ALIAS_CUE.finditer(text):
        before = text[max(0, cue.start() - 40):cue.start()].rstrip()
        if not (ALIAS_CONTEXT.search(before) or any(name in before for name in known)):
            continue
        if re.search(r'神女|神灵|皇帝|玉帝|元君[，、]?$', before[-12:]):
            continue
        cursor = cue.end()
        while item := ALIAS_ITEM.match(text, cursor):
            group = 'quoted' if item['quoted'] else 'plain'
            yield *item.span(group), 'alias'
            cursor = item.end()
            if text[cursor:cursor + 1] != '、':
                break
            cursor += 1


def candidates(text, existing, known):
    for pattern, method in ((DESTINATION, 'destination'), (INTRO, 'description'), (HERITAGE, 'inscription')):
        for match in pattern.finditer(text):
            yield *match.span('name'), method
    for match in GATE_CONTEXT.finditer(text):
        yield *match.span('left' if match['left'] else 'right'), 'gate_context'
    yield from aliases(text, known)

    for entity in existing:
        if entity['entity_type'] != 'POI':
            continue
        tail = text[entity['end']:]
        suffix = EXTEND.match(tail) or (STONE_EXTEND.match(tail) if entity['text'].endswith('石') else None)
        if suffix:
            yield entity['start'], entity['end'] + suffix.end(), 'boundary'

    for field in FIELD.finditer(text):
        for part in re.finditer(r'[^、，,／/→]+', field[1]):
            if span := named_span(part[0], field.start(1) + part.start()):
                yield *span, 'labelled_route'

    offset = 0
    for raw in text.splitlines(keepends=True):
        line = raw.strip()
        start = offset + len(raw) - len(raw.lstrip())
        offset += len(raw)
        pair = HEADING_PAIR.fullmatch(line)
        if pair:
            yield start + pair.start('alias'), start + pair.end('alias'), 'heading_alias'
        for heading in re.finditer(r'[^与、]+', line):
            if PLACE.fullmatch(heading[0]):
                yield start + heading.start(), start + heading.end(), 'heading'
        if timed := TIMED.match(raw):
            for part in re.finditer(r'[^/／、]+', raw[timed.end():]):
                if span := named_span(part[0], offset - len(raw) + timed.end() + part.start()):
                    yield *span, 'timed_stop'
        separators = list(ROUTE.finditer(line))
        if not separators or not ('→' in line or len(separators) >= 2 or '路线' in line):
            continue
        # 保留路线起点，标题前缀、计时和括注用自己的边界处理。
        cursor = max(line.rfind('：', 0, separators[0].start()), line.rfind(':', 0, separators[0].start())) + 1
        for delimiter in [*separators, None]:
            stop = delimiter.start() if delimiter else len(line)
            if span := named_span(line[cursor:stop], start + cursor, trim_route=True):
                yield *span, 'route_node'
            cursor = delimiter.end() if delimiter else stop


def allowed(name, method, stop, generic):
    if not NAME.fullmatch(name) or PHRASE.search(name) or v4.NON_NAME.search(name):
        return False
    if name in stop['off_scenic'] or any(word in name for word in stop['off_scenic']):
        return False
    if GATE.fullmatch(name):
        return method in {'gate_context', 'labelled_route', 'route_node', 'timed_stop'}
    if name in generic or re.search(r'索道|小火车|地铁|轻轨\d|公交|分钟|小时', name) and not name.endswith('站'):
        return False
    if method == 'timed_stop' and not (PLACE.fullmatch(name) or name.endswith('咖啡')):
        # 双节点行程常有无常见后缀的碑刻名，须由标题或命名语境另行确认。
        return False
    if method == 'timed_stop' and re.match(r'^(?:石刻|题刻|碑刻)', name):
        return False
    if len(name) == 2 and method in {'heading', 'destination', 'description'}:
        tokens = list(v3.jieba.posseg.cut(name))
        if len(tokens) == 1 and tokens[0].flag.startswith(('a', 'd', 'v')):
            return False
    return True


def merge(text, proposals, existing):
    kept = list(existing)
    for entity in sorted(proposals, key=lambda e: (e['start'] - e['end'], e['start'])):
        left, right = entity['start'], entity['end']
        overlap = [e for e in kept if left < e['end'] and e['start'] < right]
        if overlap:
            if len(overlap) != 1 or overlap[0]['entity_type'] != 'POI':
                continue
            old = overlap[0]
            expands = left == old['start'] and right > old['end']
            trims_station_label = (entity['method'] == 'v5_route_node' and left == old['start']
                                   and text[right:old['end'] + 1] == '站点' and right + 1 == old['end'])
            # 明确的结构边界才可以改写既有POI。禁止跨越交通、时间或两个地名。
            if not trims_station_label and not (expands and entity['method'] == 'v5_boundary'):
                continue
            kept.remove(old)
        kept.append(entity)
    return sorted(kept, key=lambda e: (e['start'], e['end']))


def extract(records, groups, stop, scenic):
    previous, per_doc = v3.extract(records, groups, stop, scenic)
    by_doc = defaultdict(list)
    for entity in previous:
        by_doc[entity['doc_id']].append(entity)
    generic = GENERIC | stop['suffix_noise'] | stop['generic_place']
    result = []
    for record in records:
        doc, text = record['doc_id'], record['clean_text']
        old = by_doc[doc]
        known = {e['text'] for e in old if e['entity_type'] == 'POI'}
        sentences = base.split_sentences(text)
        proposals = []
        for start, end, method in candidates(text, old, known):
            name = text[start:end]
            if allowed(name, method, stop, generic):
                proposals.append(base.decorate({
                    'doc_id': doc, 'scenic_id': scenic, 'entity_type': 'POI', 'text': name,
                    'subtype': method, 'method': 'v5_' + method, 'start': start, 'end': end,
                    'sentence_id': base.sentence_of(sentences, start),
                }, groups))
        entities = merge(text, proposals, old)
        result.extend(entities)
        per_doc[doc].update(entities=len(entities), by_type=dict(Counter(e['entity_type'] for e in entities)))
    return result, per_doc


if __name__ == '__main__':
    v3.main(version='v5', extractor=extract)

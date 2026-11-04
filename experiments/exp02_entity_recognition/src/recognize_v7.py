"""补充具有明确命名、路线角色或景区类别线索的景点。"""

import re
from collections import Counter, defaultdict

import recognize_entities as base
import recognize_v3 as v3
import recognize_v5 as v5
import recognize_v6 as v6


NAME = rf'{v5.CJK}{{2,16}}'
QUOTE = rf'[“”「《"](?P<name>{NAME})[“”」》"]'
NAMED = rf'{v5.CJK}{{1,13}}?(?:{v6.HEAD}|佛|之墓)'
HERITAGE = re.compile(rf'{QUOTE}\s*(?:石刻|刻石|碑刻|匾额|题刻)')
TITLES = re.compile(
    rf'(?:题名|题字|题写|题额|题|刻写)(?:的|为|是)?\s*(?:{QUOTE}|(?P<plain>{NAME}?))'
    r'(?=\s*(?:[，、；。]|等(?:石刻|碑刻|题刻)))'
)
INTERPRETED = re.compile(rf'(?:石刻|题刻|碑刻)[，、 ]?(?:被)?(?:释为|解读为|题作)\s*{QUOTE}')
NAMING = re.compile(
    rf'(?:[，；。]\s*名|(?:原|曾|历史上)名为|(?:[唐宋元明清]代|早年|旧时)\s*为)'
    rf'(?P<name>{NAMED})(?=[，。；、])'
)
ROUTE_LABEL = re.compile(
    rf'(?:自(?P<origin>{NAMED}|{v5.CJK}{{2,5}})至|(?:再|又)至)(?P<end>{NAMED})为{QUOTE}'
)
POI_LIST = re.compile(
    r'(?:景点|景观)(?:的)?(?:名字|名称)[，、：:\s]*(?:比如|例如|如)?[“「]'
    r'(?P<names>[^”」\n]{2,70})[”」]'
)
ROUTE_ROLE = re.compile(
    rf'(?:终点站(?:为|是)?|始发站(?:为|是))(?P<name>{NAME})(?=[，。；\s]|$)'
)
GATES = re.compile(r'[东南西北]门')
GATE_PAIR = re.compile(r'(?P<left>[东南西北]门)[和与及](?P<right>[东南西北]门)(?=的车|进出|出入)')
POI_CONTEXT = re.compile(
    rf'(?:小景点|一处|坐去|(?:可以|还要|想)去)(?P<name>{NAMED})'
    r'(?=景点|的车|(?:刚好|暂时|已经)?(?:关闭|封闭|开放)|和对面的)'
)
POI_SUBJECT = re.compile(
    rf'(?:^|[。；，\n])\s*(?P<name>{NAMED})'
    r'(?=如(?:同|同一座|一座|大)|似(?:众|一|群)|是[^，。]{1,22}(?:品牌|地标|景点|博物馆))'
)
FULL_NAME = re.compile(
    rf'(?:[，；。\n]|^)(?:位于{NAME}内的)?(?P<name>{NAMED})(?=，?(?:始建|修建|建于)|是[^，。]{{1,22}}(?:主题博物馆|品牌))'
)
UNNAMED_ROUTE = re.compile(r'前往|设在|设于|附近|就到|开始|可以|到达|的时候|是因为|(?:^|[是为])终点|发车|下车')


def proposals(text):
    for pattern, method in (
            (HERITAGE, 'inscription'), (INTERPRETED, 'inscription'), (NAMING, 'named_place'),
            (ROUTE_ROLE, 'route_role'), (POI_CONTEXT, 'location'), (POI_SUBJECT, 'location'),
            (FULL_NAME, 'full_name')):
        for match in pattern.finditer(text):
            yield *match.span('name'), method
    for sentence in re.finditer(r'[^。！？；\n]+', text):
        if not re.search(r'(?:等|的)(?:石刻|碑刻|题刻)|刻石|匾额', sentence[0]):
            continue
        for match in TITLES.finditer(sentence[0]):
            start, end = match.span('name' if match['name'] else 'plain')
            yield sentence.start() + start, sentence.start() + end, 'inscription'
    for match in ROUTE_LABEL.finditer(text):
        yield *match.span('name'), 'route_label'
        if match['origin']:
            yield *match.span('origin'), 'route_endpoint'
        yield *match.span('end'), 'route_endpoint'
    for match in POI_LIST.finditer(text):
        for item in re.finditer(NAME, match['names']):
            yield match.start('names') + item.start(), match.start('names') + item.end(), 'named_list'
    for match in GATE_PAIR.finditer(text):
        for group in ('left', 'right'):
            yield *match.span(group), 'gate_context'
    for match in re.finditer(rf'(?m)^\s*(?P<name>{v5.CJK}{{2,13}}之墓)\s*$', text):
        yield *match.span('name'), 'heading'


def allowed(name, method, stop, generic):
    if method == 'gate_context':
        return bool(GATES.fullmatch(name))
    if method in {'inscription', 'route_label', 'named_list'}:
        # 明确的题名和枚举语境允许含动作字的名称。
        return bool(v5.NAME.fullmatch(name)) and name not in generic and name not in stop['off_scenic']
    if method == 'route_role' and UNNAMED_ROUTE.search(name):
        return False
    if name.startswith(('位于', '坐落', '座落', '位在')):
        return False
    return v5.allowed(name, method, stop, generic)


def extract(records, groups, stop, scenic):
    previous, per_doc = v6.extract(records, groups, stop, scenic)
    by_doc = defaultdict(list)
    for entity in previous:
        by_doc[entity['doc_id']].append(entity)
    generic = v5.GENERIC | stop['suffix_noise'] | stop['generic_place']
    result = []
    for record in records:
        doc_id, text = record['doc_id'], record['clean_text']
        sentences = base.split_sentences(text)
        kept = by_doc[doc_id]
        for start, end, method in sorted(proposals(text), key=lambda item: (item[0] - item[1], item[0])):
            name = text[start:end]
            if not allowed(name, method, stop, generic):
                continue
            overlap = [e for e in kept if start < e['end'] and e['start'] < end]
            if overlap:
                if method != 'full_name' or len(overlap) != 1:
                    continue
                old = overlap[0]
                if old['entity_type'] != 'POI' or not (start < old['start'] and end == old['end']):
                    continue
                kept.remove(old)
            kept.append(base.decorate({
                'doc_id': doc_id, 'scenic_id': scenic, 'entity_type': 'POI', 'text': name,
                'subtype': method, 'method': f'v7_{method}', 'start': start, 'end': end,
                'sentence_id': base.sentence_of(sentences, start),
            }, groups))
        kept.sort(key=lambda entity: (entity['start'], entity['end']))
        result.extend(kept)
        per_doc[doc_id].update(entities=len(kept), by_type=dict(Counter(e['entity_type'] for e in kept)))
    return result, per_doc


if __name__ == '__main__':
    v3.main(version='v7', extractor=extract)

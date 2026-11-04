"""从题名与位置语境补充 v5 的候选，保留原文字符位置。"""

import re
from collections import Counter, defaultdict

import recognize_entities as base
import recognize_v3 as v3
import recognize_v5 as v5


HEADS = v5.HEADS | {'亭子', '御道', '山门', '峰林', '摩崖', '配殿', '园林', '林', '库'}
HEAD = '|'.join(sorted(HEADS, key=lambda name: (-len(name), name)))
PLACE = rf'{v5.CJK}{{1,15}}?(?:{HEAD})'
RIGHT = (r'(?=$|[\s，。；、！？（）]|之间|一带|旁边|附近|下方|上方|脚下|下面|'
         r'里有|进出|入园|出园|下车|前往|走走|(?:暂时|已经|目前|刚好)?(?:关闭|封闭|开放)|景点)')
POSITION = re.compile(
    rf'(?:坐落[在于]|座落[在于]|位于|临近|紧邻|过了|走的是|旁边的|对面的|'
    rf'取景地|旁的|以[东南西北]有|(?:可以|想|再|还要)去)'
    rf'(?P<name>{PLACE}){RIGHT}'
)
BETWEEN = re.compile(
    rf'(?:坐落[在于]|座落[在于]|位于)(?P<left>{PLACE})[和与及](?P<right>{PLACE})(?=之间)'
)
REGIONAL_PREFIX = re.compile(rf'^{v5.CJK}{{2,8}}?[东南西北]麓(?={v5.CJK}{{2,10}}(?:村|寨|镇)$)')
NAMING = re.compile(
    rf'(?:称为|名为|叫作|题名为|改称)(?P<name>{PLACE})(?=$|[\s，。；、！？])'
)
STOP_ALIAS = re.compile(
    rf'^\s*第[一二三四五六七八九十\d]+站[:：]\s*{PLACE}\s*[（(]'
    rf'(?P<name>{v5.CJK}{{2,16}})[）)]\s*$',
    re.MULTILINE,
)
QUOTED = re.compile(r'“([^”\n]+)”|「([^」\n]+)」|《([^》\n]+)》|"([^"\n]+)"')
INSCRIPTION = r'石刻|刻石|碑刻|石碑|摩崖|匾额|题刻|碑铭'
INSCRIPTION_BEFORE = re.compile(rf'(?:{INSCRIPTION})[^。！？；\n]{{0,18}}(?:写着|刻着|刻有|题有|题写)(?:的)?\s*$')
INSCRIPTION_AFTER = re.compile(rf'^\s*(?:的)?(?:{INSCRIPTION})')
NAMING_BEFORE = re.compile(r'(?:又名|又叫|旧称|旧名|俗称|人称(?:此为|其为)|人们称(?:之|其|它们)?为)\s*$')
PLACE_CONTEXT = re.compile(rf'(?:{HEAD}|景观|地标|景点)(?:[，、 ]|是|被|亦|当地|人们|常|古时){{0,8}}$')
NON_NAME = re.compile(r'^[一二两三四五六七八九十几\d]+(?:次|趟|回)|的')
SEASONS = re.compile(r'初春|暮春|盛夏|初秋|深秋|隆冬|寒冬|暑假|寒假|旺季|淡季')
CALENDAR = re.compile(rf'{v3.LEFT}{v3.NUM}月底|(?:大年|正月)初[一二三四五六七八九十]')


def poi_spans(text):
    between = {match.span(): match for match in BETWEEN.finditer(text)}
    for pattern in (POSITION, NAMING, STOP_ALIAS):
        for match in pattern.finditer(text):
            if match.span() in between:
                continue
            start, end = match.span('name')
            if prefix := REGIONAL_PREFIX.match(match['name']):
                start += prefix.end()
            yield start, end, 'location'
    for match in between.values():
        for group in ('left', 'right'):
            yield *match.span(group), 'location'
    for match in QUOTED.finditer(text):
        start, end = match.span(match.lastindex)
        before = text[max(0, match.start() - 40):match.start()]
        after = text[match.end():match.end() + 8]
        if INSCRIPTION_BEFORE.search(before) or INSCRIPTION_AFTER.match(after):
            yield start, end, 'inscription'
        elif cue := NAMING_BEFORE.search(before):
            if PLACE_CONTEXT.search(before[:cue.start()]):
                yield start, end, 'place_alias'


def extract(records, groups, stop, scenic):
    previous, per_doc = v5.extract(records, groups, stop, scenic)
    by_doc = defaultdict(list)
    for entity in previous:
        by_doc[entity['doc_id']].append(entity)
    generic = v5.GENERIC | stop['suffix_noise'] | stop['generic_place']
    result = []
    for record in records:
        doc_id, text = record['doc_id'], record['clean_text']
        sentences = base.split_sentences(text)
        proposals = []
        for start, end, method in poi_spans(text):
            name = text[start:end]
            if not v5.allowed(name, method, stop, generic) or NON_NAME.search(name):
                continue
            proposals.append((start, end, 'POI', method))
        for pattern, subtype in ((SEASONS, 'period'), (CALENDAR, 'day')):
            for match in pattern.finditer(text):
                if v3.time_allowed(text, *match.span(), subtype):
                    proposals.append((*match.span(), 'TIME', subtype))

        kept = list(by_doc[doc_id])
        for start, end, kind, method in sorted(proposals, key=lambda item: (item[0] - item[1], item[0])):
            if any(start < entity['end'] and entity['start'] < end for entity in kept):
                continue
            kept.append(base.decorate({
                'doc_id': doc_id, 'scenic_id': scenic, 'entity_type': kind,
                'text': text[start:end], 'subtype': method, 'method': f'v6_{method}',
                'start': start, 'end': end, 'sentence_id': base.sentence_of(sentences, start),
            }, groups))
        kept.sort(key=lambda entity: (entity['start'], entity['end']))
        result.extend(kept)
        per_doc[doc_id].update(entities=len(kept), by_type=dict(Counter(e['entity_type'] for e in kept)))
    return result, per_doc


if __name__ == '__main__':
    v3.main(version='v6', extractor=extract)

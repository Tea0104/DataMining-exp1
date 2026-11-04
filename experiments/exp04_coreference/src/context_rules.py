"""v3篇章规则：扩展原文短语、路线及事件；不读取标注或按文档编号分支。"""
import re

from common import span

PLACE_SUFFIXES = ('国家森林公园', '国家级风景名胜区', '公园', '景区', '广场', '码头',
                  '石坊', '牌坊', '寺', '庙', '桥', '园', '坊', '阁', '殿', '站', '路口', '步道')
MOTION = re.compile(r'^(?:从|由|沿着|穿过)')
EVENT = re.compile(r'升起|落下|出发|抵达|驶入|启动|开动|到站|开始|结束|开幕|闭幕|冲出|出现|发生')


def expand_candidates(text, candidates):
    result = {(c['start'], c['end'], c['entity_type']): dict(c) for c in candidates}

    def add(start, end, kind, source, **extra):
        if start < end:
            result[(start, end, kind)] = span(text, start, end, entity_type=kind, source=source, **extra)

    for candidate in candidates:
        if candidate['entity_type'] != 'place':
            continue
        for suffix in ('石坊', '牌坊', '客运站', '坊'):
            if text.startswith(suffix, candidate['end']) and not candidate['text'].endswith(suffix):
                add(candidate['start'], candidate['end'] + len(suffix), 'place', 'context_named_place',
                    expanded_from=candidate['text'])
    # 短标题、图注和复合地名（“某园暨某中心”）本身是实际名词短语。
    for line in re.finditer(r'[^\n]+', text):
        raw = line.group()
        first = re.split(r'[，,。暨]', raw.strip(), maxsplit=1)[0]
        first = re.split(r'[—：:【】]', first)[-1].strip()
        if (2 <= len(first) <= 18 and re.fullmatch(r'[\u4e00-\u9fff]+', first)
                and first.endswith(PLACE_SUFFIXES)
                and not re.search(r'到|从|走|看|有|里|的|在|过|去|是', first)):
            start = line.start() + raw.find(first)
            add(start, start + len(first), 'place', 'context_named_place', standalone=raw.strip() == first)
        # 文首标题中的景区全称可以作为篇章主题，允许在明确主题回指时跨越普通窗口。
        if line.start() < 80:
            for match in re.finditer(r'[\u4e00-\u9fff]{2,12}(?:国家森林公园|国家级风景名胜区)', raw):
                add(line.start() + match.start(), line.start() + match.end(), 'place', 'document_topic')

    # 已明确为地点的名称，后续再次出现时不受POS误分成人名影响。
    established_places = {c['text'] for c in result.values()
                          if c['source'] in ('context_named_place', 'exp02_v2') and c['entity_type'] == 'place'}
    for name in established_places:
        for match in re.finditer(re.escape(name), text):
            key = (match.start(), match.end(), 'place')
            if key not in result:
                add(match.start(), match.end(), 'place', 'context_named_place', type_evidence='repeated_place')

    # 名词中心词后的修饰短语不应造成只取某个地点，路线保留完整连续跨度。
    for sentence in re.finditer(r'[^。！？!?；;\n]+', text):
        clauses = list(re.finditer(r'[^，,]+', sentence.group()))
        for index, clause in enumerate(clauses):
            content = clause.group().strip()
            if not MOTION.match(content):
                continue
            start = sentence.start() + clause.start() + len(clause.group()) - len(clause.group().lstrip())
            end = sentence.start() + clause.end()
            for following in clauses[index + 1:]:
                if not re.match(r'\s*(?:再|然后|接着|继续|步行)', following.group()):
                    break
                end = sentence.start() + following.end()
            add(start, end, 'route', 'movement_route')
    # 连续的带时刻移动记录，构成前后两站间的行走过程。
    timed_line = r'\d{1,2}点(?:\d{1,2}分|半)?(?:走到|到达|抵达)[^。！？\n]+'
    for match in re.finditer(rf'{timed_line}\s*\n\s*{timed_line}', text):
        add(match.start(), match.end(), 'route', 'timed_movement_route')

    # 箭头序列仅保留连续地点，排除“索道上山”等操作；不把全篇地名混成一组。
    all_places = [c for c in result.values() if c['entity_type'] == 'place']
    for match in re.finditer(r'[\u4e00-\u9fffA-Za-z0-9]{1,24}(?:[→⇒➜][\u4e00-\u9fffA-Za-z0-9]{1,24})+', text):
        runs, current = [], []
        for part in re.finditer(r'[^→⇒➜]+', match.group()):
            start, end = match.start() + part.start(), match.start() + part.end()
            named = any(c['start'] == start and c['end'] == end for c in all_places)
            if named and not re.search(r'上山|下山|乘坐|步行', part.group()):
                current.append((start, end))
            else:
                if len(current) > 1:
                    runs.append(current)
                current = []
        if len(current) > 1:
            runs.append(current)
        for run in runs:
            add(run[0][0], run[-1][1], 'place_group', 'arrow_place_group')

    for clause in re.finditer(r'[^，,。！？!?；;\n]+', text):
        value = clause.group().strip()
        start = clause.start() + len(clause.group()) - len(clause.group().lstrip())
        if 4 <= len(value) <= 100 and EVENT.search(value):
            add(start, clause.end(), 'event', 'transition_event')
        condition = re.match(r'如果(?:是)?(.+)', value)
        if condition:
            add(start + condition.start(1), start + condition.end(1), 'event', 'conditional_scenario')
    return sorted(result.values(), key=lambda c: (c['start'], c['end'], c['entity_type']))


def latest_mentions(candidates):
    """复用同名提及的类型证据，但返回最近一次原文位置。"""
    groups = {}
    for candidate in candidates:
        groups.setdefault((candidate['entity_type'], candidate['text']), []).append(candidate)
    result = []
    for group in groups.values():
        newest = dict(max(group, key=lambda c: (c['end'], c['start'])))
        if any(c['source'] == 'exp02_v2' for c in group):
            newest['type_evidence'] = 'exp02_v2'
        result.append(newest)
    return result


def choose_context(sample, text, candidates, fallback, max_distance=400):
    p = sample['pronoun']
    previous = [c for c in candidates if c['end'] <= p['start'] and p['start'] - c['end'] <= max_distance]
    local = latest_mentions(previous)
    tail = text[p['end']:p['end'] + 40]

    def select(pool, reason):
        winner = max(pool, key=lambda c: (c['end'], len(c['text'])))
        return winner, reason, [{'candidate': winner, 'score': None, 'reasons': [reason]}]

    if sample['pronoun_type'] == 'demonstrative' and re.match(r'(?:几|多)?个?(?:地方|地点|景点|站点)', tail):
        group = [c for c in previous if c['entity_type'] == 'place_group']
        if group:
            return select(group, '复数地点回指最近的连续路线景点集合')

    if sample['pronoun_type'] == 'demonstrative' and re.match(r'(?:段|条)(?:台阶)?(?:游览)?路', tail):
        routes = [c for c in previous if c['entity_type'] == 'route']
        # 当前句的“从A到B这段路”在代词前结束，补取该句前缀。
        sentence_start = max(text.rfind(mark, 0, p['start']) for mark in '。！？!?；;\n') + 1
        prefix = text[sentence_start:p['start']].strip(' ，,')
        if MOTION.match(prefix):
            start = sentence_start + text[sentence_start:p['start']].find(prefix)
            # 只扩展实际的连续移动分句，描述性分句不并入路线。
            pieces = list(re.finditer(r'[^，,]+', prefix))
            end = pieces[0].end()
            for piece in pieces[1:]:
                if not re.match(r'\s*(?:再|然后|接着|继续|步行)', piece.group()):
                    break
                end = piece.end()
            return select([span(text, start, start + end, entity_type='route', source='current_movement_prefix')],
                          '路段回指保留起点、终点及连续移动过程')
        if routes:
            return select(routes, '路段回指最近完整移动过程，而非最后一个地点')

    if sample['pronoun_type'] == 'demonstrative' and re.match(r'(?:一瞬间|一刻)', tail):
        events = [c for c in previous if c['source'] == 'transition_event']
        if events:
            return select(events, '时刻指示关联最近的状态变化事件')
    if sample['pronoun_type'] == 'demonstrative' and re.match(r'是(?:另外|另一|又一)', tail):
        events = [c for c in previous if c['source'] == 'conditional_scenario']
        if events:
            return select(events, '概括性指代关联前面的完整条件场景')

    if sample['pronoun_type'] == 'demonstrative' and re.match(r'位置|地方|地点', tail):
        places = [c for c in local if c['entity_type'] == 'place']
        if places:
            return select(places, '位置指示优先最近地点，而非价格等邻近物体')

    # “走这里去某处”的短图注不能仅凭目的地反推未命名岔路。
    line_start, line_end = text.rfind('\n', 0, p['start']) + 1, text.find('\n', p['end'])
    line = text[line_start:line_end if line_end >= 0 else len(text)]
    if (sample['pronoun_type'] == 'location' and len(line.strip()) <= 30
            and re.match(r'(?:走|从)?(?:这里|那里|这边|那边)(?:去|往)', line.strip())):
        paths = [c for c in local if c['entity_type'] in ('place', 'route')
                 and c['text'].endswith(('路口', '岔路', '小路', '步道', '通道', '栈道', '桥'))]
        if paths:
            return select(paths, '指路表达有明确前置道路名')
        return None, '短图注依赖现场路径，正文无明确道路先行词', []
    if sample['pronoun']['text'] == '此' and re.match(r'题|观', tail):
        noun = '题刻' if tail.startswith('题') else '观'
        matching = [c for c in local if c['text'].endswith(noun)]
        if not matching:
            return None, '指示限定或现场景观，缺少明确前文同类名词', []

    # “X有A、B；这是……公园”应回到主语X，不能取列举末项B。
    if sample['pronoun_type'] == 'demonstrative' and re.match(r'是[^。\n]{0,65}(?:公园|景区|寺庙|博物馆)', tail):
        start = max(text.rfind(mark, 0, p['start']) for mark in '。！？!?\n') + 1
        subjects = [c for c in previous if c['entity_type'] == 'place' and c['start'] >= start
                    and re.match(r'有|以', text[c['end']:c['end'] + 1])]
        if subjects:
            return select(subjects, '概括句回指列举内容的主语')
    if sample['pronoun_type'] == 'demonstrative' and re.match(r'就是|是', tail):
        adjacent = [c for c in local if c['entity_type'] in ('place', 'object')
                    and p['start'] - c['end'] <= 2]
        if adjacent:
            return select(adjacent, '判断句优先最近完整名词短语')

    if sample['pronoun_type'] == 'location':
        if sample['pronoun']['text'] in ('该园', '该景区'):
            suffixes = ('园', '公园', '景区', '风景区')
            subjects = []
            for clause in re.finditer(r'[^。！？!?\n]+', text[max(0, p['start'] - max_distance):p['start']]):
                locator = re.search(r'坐落在|位于|地处', clause.group())
                if locator:
                    start = max(0, p['start'] - max_distance) + clause.start()
                    end = start + locator.start()
                    subjects += [c for c in local if c['entity_type'] == 'place'
                                 and start <= c['start'] < c['end'] <= end and c['text'].endswith(suffixes)]
            if subjects:
                return select(subjects, '该园回指地址介绍的主语，排除地址中的城市和上级公园')
        captions = [c for c in local if c.get('standalone') and p['start'] - c['end'] <= 20]
        if captions and re.match(r'\s*(?:走到|到|在|来)?(?:这里|那里|此处)', line):
            return select(captions, '当前地点延续紧邻的独立地点标题或图注')
        nearby_text = text[max(0, p['start'] - 140):p['start']]
        if re.search(r'游玩方式|游览方式|景区交通|园区很大', nearby_text):
            topics = [c for c in candidates if c['source'] == 'document_topic' and c['end'] <= p['start']]
            if topics:
                return select(topics, '全园游览讨论回指文首景区主题')

    # 优先完整地名边界，移除“某峪坊”中被分词截短的“某峪”。
    expanded = [c for c in local if c['source'] == 'context_named_place']
    local = [c for c in local if not any(c['entity_type'] == 'place' and e['start'] == c['start']
                                       and e['end'] > c['end'] for e in expanded)]
    # 非路线/事件指示仍使用类型约束；同名提及只在历史范围内折叠。
    nominal = [c for c in local if c['entity_type'] not in ('route', 'event', 'place_group')]
    return fallback(sample, text, nominal, 'v3_fallback', max_distance)

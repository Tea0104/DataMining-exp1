"""v4：指代意图分类、篇章主题、完整名词短语与事件框架。推理不读取标注。"""
import re

from common import span

NOMINAL_ENDS = {
    'building': ('寝宫楼', '阁楼', '楼', '亭', '殿', '寺', '庙'),
    'inscription': ('石碑', '碑刻', '石刻', '题刻', '碑'),
    'plant': ('姊妹松', '松树', '柏树', '银杏树', '大树', '古树', '树', '松'),
    'animal': ('猕猴', '猴子', '松鼠', '鸬鹚', '鸟类', '梅花鹿'),
    'person': ('工作人员', '摄影师', '售票员', '搬运工', '工人', '大哥', '司机', '游客', '游人', '皇帝'),
    'place': ('小广场', '观景台', '景区', '公园', '寺', '庙', '瀑', '溪', '湾', '路口', '检查站', '广场'),
}


def window_start(text, end, marks='。！？!?\n'):
    return max(text.rfind(mark, 0, end) for mark in marks) + 1


def expand_discourse(record, candidates):
    text = record['clean_text']
    pool = {(c['start'], c['end'], c['entity_type']): dict(c) for c in candidates}

    def add(start, end, kind, source, **extra):
        if start < end:
            key = (start, end, kind)
            if key not in pool or source == 'section_topic':
                pool[key] = span(text, start, end, entity_type=kind, source=source, **extra)

    # 以完整标点分句为边界，提取引入的主题名词，不把城市地址当作被介绍的场所。
    for line in re.finditer(r'[^\n]+', text):
        stripped = line.group().strip(' ■①②③④⑤⑥⑦⑧⑨⑩、')
        offset = line.start() + line.group().find(stripped) if stripped else line.start()
        lead = re.match(r'([\u4e00-\u9fff]{2,7})，', stripped)
        if lead and lead.group(1).endswith(('洞', '瀑', '湾', '剑', '庙', '寺', '亭', '湖')):
            add(offset, offset + len(lead.group(1)), 'place', 'section_topic')
        subject = re.match(r'[^，。\n]{1,16}的([\u4e00-\u9fff]{2,5}(?:洞|寺|庙|亭|湖))，', stripped)
        if subject:
            add(offset + subject.start(1), offset + subject.end(1), 'place', 'section_topic')
        if (2 <= len(stripped) <= 9 and re.fullmatch(r'[\u4e00-\u9fff]+', stripped)
                and not re.search(r'的|看到|走过|到达|我们|继续|相传', stripped)
                and (any(stripped.endswith(v) for values in NOMINAL_ENDS.values() for v in values)
                     or stripped.endswith(('峰', '洞', '阁', '祠', '剑'))
                     or any(c['start'] == offset and c['end'] == offset + len(stripped)
                            and c['entity_type'] == 'place' for c in candidates))):
            kind = 'plant' if stripped.endswith(NOMINAL_ENDS['plant']) else 'place'
            add(offset, offset + len(stripped), kind, 'section_topic')
        for match in re.finditer(r'[\u4e00-\u9fff]{2,16}(?:游览线路|游览路线|游览线|游览路|登山线路|登山路线|线路|路线)', line.group()):
            phrase = re.split(r'从|称为|即|就是|是|选择了|目前|的|条|这|那|也写得', match.group())[-1]
            if len(phrase) >= 3 and not re.search(r'怎么|没有|难度|全程|恢复|过|经典|登顶|选择|重复|为了|便捷', phrase):
                add(line.start() + match.end() - len(phrase), line.start() + match.end(), 'route', 'named_route')
        # 省略式罗列同样可组成完整路线，“A—B—C”不只识别最后一站。
        for match in re.finditer(r'[\u4e00-\u9fff]{2,12}(?:[—–－-][\u4e00-\u9fff]{2,12}){2,}', line.group()):
            value = re.sub(r'^(?:即|从|经由|途经)', '', match.group())
            add(line.start() + match.end() - len(value), line.start() + match.end(), 'route', 'dash_route')
        definition = re.search(r'路线是([^，。\n]+)', line.group())
        if definition and re.search(r'[—-]', definition.group(1)):
            add(line.start() + definition.start(1), line.start() + definition.end(1), 'route', 'defined_route')
    # 通过已有名词候选及常见中心词重建短语；避免POS把猕猴、游人或碑误判成人名。
    for kind, endings in NOMINAL_ENDS.items():
        for ending in sorted(endings, key=len, reverse=True):
            for match in re.finditer(re.escape(ending), text):
                start, end = match.start(), match.end()
                if kind in ('inscription', 'plant') and len(ending) == 1:
                    if (start and text[start - 1] in '该此这其') or text[end:end + 1] in ('顶', '刻'):
                        continue
                if kind in ('building', 'inscription'):
                    left = max(text.rfind(ch, 0, start) for ch in '。！？\n，,、：:“”"') + 1
                    fragment = text[left:end]
                    fragment = re.split(r'是|为|有|称|叫|的|分|上刻', fragment)[-1]
                    if 1 < len(fragment) <= 12 and re.fullmatch(r'[\u4e00-\u9fff]+', fragment):
                        start = end - len(fragment)
                add(start, end, kind, 'nominal_head')
    # 已知地名后紧连功能后缀时合并，避免把“某地小广场”截成某地。
    for c in candidates:
        if c['entity_type'] == 'place' and len(c['text']) >= 2:
            suffix = re.match(r'小广场|景区|公园|检查站|索道[A-C]?线', text[c['end']:])
            if suffix:
                add(c['start'], c['end'] + suffix.end(), 'place', 'extended_place')
    for match in re.finditer(r'[\u4e00-\u9fff·]{2,15}酒店(?:（[^）\n]+）)?', text):
        value = re.split(r'预定的|订的|住的|就是|回到', match.group())[-1]
        if not re.search(r'下图|附上|打车|回|到|我们|对面|早|后来|准备', value):
            add(match.end() - len(value), match.end(), 'hotel', 'named_nominal')
    for match in re.finditer(r'[\u4e00-\u9fff]{0,6}(?:湾|门|站)(?:有个|外就是)[^。\n]{0,15}(?:检查站|所在地)', text):
        add(match.start(), match.end(), 'place', 'located_facility')
    for match in re.finditer(r'[\u4e00-\u9fff]{2,8}(?:演出|表演)的地方', text):
        add(match.start(), match.end(), 'place', 'located_facility')
    for match in re.finditer(r'[“"]([^”"\n]{2,10})[”"]', text):
        if re.match(r'石刻|石坊|[，。]', text[match.end():]) or re.search(r'上面写着|石坊为|上刻', text[max(0, match.start()-12):match.start()]):
            add(match.start(1), match.end(1), 'inscription', 'quoted_object_name')
        if re.search(r'石坊为', text[max(0,match.start()-8):match.start()]):
            add(match.start(1), match.end(1), 'place', 'quoted_place_name')
        if match.group(1).endswith(('泉', '池')):
            add(match.start(1), match.end(1), 'water', 'quoted_water_name')
    plant = r'[\u4e00-\u9fff]{1,5}(?:树|松)'
    for match in re.finditer(rf'{plant}(?:和|与|、){plant}', text):
        add(match.start(), match.end(), 'plant_group', 'coordinated_plants')
    for match in re.finditer(r'\d+位皇帝|\d+[-—至]\d+排', text):
        add(match.start(), match.end(), 'person_group' if '皇帝' in match.group() else 'position_group', 'quantified_group')
    for match in re.finditer(r'(?:特意)?选择了(从[^，。\n]{2,30}(?:上山|下山))', text):
        add(match.start(1), match.end(1), 'route', 'chosen_route')
    for match in re.finditer(r'也是([^。\n]{2,40}一段(?:旅程|行程))', text):
        add(match.start(1), match.end(1), 'trip', 'nominal_trip')
    # 作者前文明确引入的地名，后文重复出现时保留相同类型。
    named = {c['text']: c['entity_type'] for c in pool.values()
             if c['source'] in ('section_topic', 'context_named_place', 'exp02_v2')
             and c['entity_type'] in ('plant', 'place') and len(c['text']) >= 2}
    for name, kind in named.items():
        for match in re.finditer(re.escape(name), text):
            if (match.start(), match.end(), kind) not in pool:
                add(match.start(), match.end(), kind, 'repeated_topic')
    return sorted(pool.values(), key=lambda c: (c['start'], c['end'], c['entity_type']))


def infer(record, sample, candidates, fallback):
    text, p = record['clean_text'], sample['pronoun']
    before, tail = text[:p['start']], text[p['end']:p['end'] + 90]
    previous = [c for c in candidates if c['end'] <= p['start']]
    local = [c for c in previous if p['start'] - c['end'] <= 500]
    topics = [c for c in previous if c['source'] == 'section_topic']
    topic = max(topics, key=lambda c: c['end']) if topics else None
    text_title = record.get('title', '')

    def result(ant, reason, kind=None, description=None, evidence_source='clean_text'):
        return {'antecedent': ant, 'reason': reason,
                'referent': {'kind': kind or (ant['entity_type'] if ant else 'unresolved'),
                             'description': description or (ant['text'] if ant else '无法确定'),
                             'evidence_source': evidence_source},
                'ranked_candidates': []}

    def pick(pool, reason, kind=None):
        if not pool:
            return None
        candidate = max(pool, key=lambda c: (c['end'], len(c['text'])))
        return result(candidate, reason, kind)

    def substantive(category):
        return [c for c in local if c['entity_type'] == category and len(c['text']) > 1
                and not re.search(r'该|此|不知道|以至于', c['text'])]

    def body_quote(value, kind='event', source='clause_frame'):
        start = before.rfind(value)
        return span(text, start, start + len(value), entity_type=kind, source=source) if start >= 0 and value else None

    def clause_before():
        value = before.rstrip(' ，,。！？\n')
        start = max(value.rfind(ch) for ch in '。！？\n') + 1
        return value[start:].strip()

    if p['text'] == '他' and before.endswith('无'):
        return result(None, '无他是固定表达，不作人物回指', 'non_pronoun', '无其他原因')
    if re.match(r'(?:一)?篇|份(?:游记|记录)', tail) or re.match(r'是[^。\n]{0,18}(?:一篇|文章)', tail):
        return result(None, '篇章自身指示', 'document', '当前文章：' + text_title, 'document')
    if re.match(r'(?:次|趟)(?:双休日)?(?:旅行|出行|旅程)', tail):
        return result(None, '行程级指代保留整次旅行', 'trip', '本文记录的出行：' + text_title, 'document')
    if re.match(r'(?:个)?季节', tail):
        return result(None, '季节指示，不把景点当作季节', 'time', '作者此次游览时的季节，确切季节需结合全文判断', 'document')
    if re.match(r'(?:一)?天(?!成)|会|时候|后', tail) and p['text'] in ('那', '这', '此'):
        if re.match(r'一天', tail) and before.endswith('走'):
            days = list(re.finditer(r'(?im)^Day\s*\d+[^\n]*', before))
            if days:
                return result(body_quote(days[-1].group(), 'time'), '日程标题确定当前游览日，跳过元话语中的残缺动词', 'time')
        event = clause_before()
        return result(body_quote(event), '时间指示关联此前事件或游览日', 'time', '前述游览或事件发生的当时：' + event)
    if re.match(r'两天', tail):
        dates = list(re.finditer(r'\d{4}[.年]\d{1,2}[.月]\d{1,2}(?:和|、|至|[-—])\d{1,2}(?:号|日)?', before))
        if dates:
            return result(body_quote(dates[-1].group(), 'time'), '复数日指示回指前文日期范围', 'time')
    if re.match(r'(?:一)?段(?!路|台阶)', tail):
        movement = [c for c in local if c['entity_type'] in ('route', 'event')]
        content = clause_before()
        if re.search(r'坐车|乘车|登顶|索道|电梯', content):
            return result(body_quote(content), '段落回指保留前文完整交通或登顶过程', 'event')
        if content in ('当然', '然而', '不过'):
            preceding = before[:before.rfind(content)].rstrip(' ，,。！？!\n')
            content = preceding[window_start(preceding, len(preceding)):]
            return result(body_quote(content), '话语连接词不替代前述活动过程', 'event')
        if movement:
            return pick(movement, '一段回指最近完整移动过程')
    if before.endswith('至') and re.match(r'[，,]', tail):
        return result(None, '至此是当前进程终点的时间指示', 'time', '本文当前游览行程完成的时点', 'discourse')
    if re.match(r'种(?!自我)[^。\n]{0,15}感觉', tail):
        value = re.split(r'感觉', tail)[0].removeprefix('种').rstrip('的') + '的游览感受'
        return result(None, '感觉类指示概括当前环境感受', 'scene', '前文游览场景中的' + value, 'discourse')
    if re.match(r'大概是[^。\n]{0,15}样子', tail):
        return result(body_quote(clause_before(), 'scene'), '样貌判断回指整幅前述场景', 'scene')
    if re.match(r'的(?:附属品|补充|核心|一部分)', tail):
        trips = [c for c in local if c['source'] == 'nominal_trip']
        if trips:
            return pick(trips, '从属关系回指完整的行程名词短语而非泛称')
    if re.match(r'(?:个)?为了[^。\n]{0,15}(?:市|城市)', tail):
        value = clause_before()
        if re.fullmatch(r'[\u4e00-\u9fff]{2,6}', value):
            return result(body_quote(value, 'place'), '同位说明紧邻城市名', 'place')
    if re.match(r'就是[^。\n]{0,8}[“"]', tail) and not re.search(r'碑', tail[:25]):
        content = clause_before()
        if re.search(r'流水|石纹|溪水|风光|景色', content):
            return result(body_quote(content, 'scene'), '命名句回指完整景观描述', 'scene')
    if re.match(r'饮水', tail):
        water = [c for c in local if c['entity_type'] == 'water']
        if water:
            return pick(water, '饮水地点指示优先水体而非人物或整座寺庙')

    # 名称、引用内容和时段的指示。
    if re.match(r'句(?:话)?', tail):
        quoted = list(re.finditer(r'[“"]([^”"\n]+)[”"]', before[-250:]))
        if quoted and before[-250:][quoted[-1].end():].strip() == '':
            return result(body_quote(quoted[-1].group(1), 'quotation'), '这句话回指紧邻的完整引语', 'quotation')
    if re.match(r'名称|名字|称呼', tail):
        names = list(re.finditer(r'[“"]([^”"\n]+)[”"]', before[-130:]))
        if names:
            value = names[-1].group(1)
            if len(names) >= 2 and re.fullmatch(r'[、，,\s]*', before[-130:][names[-2].end():names[-1].start()]):
                value = before[-130:][names[-2].start():names[-1].end()]
            return result(body_quote(value, 'name_group'), '名称指示回到前文命名内容', 'name_group')
    if re.match(r'个?时间', tail):
        matches = list(re.finditer(r'(?:预约的|预约|规定的)[^，。\n]{0,8}时间段', before))
        if matches:
            return pick([span(text, m.start(), m.end(), entity_type='time', source='appointment_time') for m in matches], '指预约入园时间段')
    if re.match(r'(?:几|\d+)排', tail):
        answer = pick([c for c in local if c['entity_type'] == 'position_group'], '排数指示匹配前文座席范围')
        if answer:
            return answer
    if re.match(r'\d+位皇帝', tail):
        answer = pick([c for c in local if c['entity_type'] == 'person_group'], '量词与群体中心词一致')
        if answer:
            return answer

    # 人物、动物及植物拟人分别处理，避免POS人名误标压过有语义证据的对象。
    if sample['pronoun_type'] in ('person', 'thing_or_animal'):
        animal = [c for c in local if c['entity_type'] == 'animal' and p['start'] - c['end'] <= 180]
        plants = [c for c in local if c['entity_type'] in ('plant', 'plant_group')]
        people = [c for c in local if c['entity_type'] == 'person'
                  and (c['source'] == 'coordinated_people' or c['text'].endswith(NOMINAL_ENDS['person'])
                       or c.get('gender') == 'female')]
        if p['text'].endswith('们') and re.search(r'(?:柏树|松树|植物|树木)', before[-150:]):
            groups = [c for c in plants if c['entity_type'] == 'plant_group']
            if groups:
                return pick(groups, '复数非人代词回指植物集合')
        if p['text'] in ('她', '她们'):
            female = [c for c in people if c.get('gender') == 'female']
            if female:
                return pick(female, '女性人物指代')
            plant_topics = [c for c in plants if c['text'].endswith(('姊妹松', '姐妹松')) or c['source'] == 'section_topic']
            if plant_topics:
                return pick(plant_topics, '植物主题中的女性代词为拟人写法', 'plant')
        if sample['pronoun_type'] == 'person':
            old = fallback()
            if old['antecedent'] and old['antecedent']['source'] == 'coordinated_people':
                return old
            if people:
                return pick(people, '有明确人物中心词的候选优先于POS猜测')
        elif animal:
            return pick(animal, '非人代词优先明确动物')
        elif topic and re.match(r'是', tail):
            return result(topic, '判断句延续当前景物主题')

    # 中心词驱动，匹配前文的同类完整短语。
    for head, category in [('楼', 'building'), ('亭', 'building'), ('碑', 'inscription'), ('树', 'plant')]:
        if re.match(head, tail):
            pool = [c for c in substantive(category) if c['text'].endswith(head)]
            if head == '树':
                pool = [c for c in pool if not re.search(r'讹为[^。\n]*$', text[max(0,c['start']-8):c['start']])]
            answer = pick(pool, '名词中心词匹配完整短语')
            if answer:
                return answer
    if re.match(r'(?:个)?(?:景区|五星级景区)|座(?:[“"]?森林之城|城市|城)', tail):
        if p['start'] and previous:
            adjacent = [c for c in previous if c['entity_type'] == 'place' and c['end'] == p['start']]
            if adjacent:
                return pick(adjacent, '同位指示限定回指紧邻地名')
        parks = [c for c in previous if c['entity_type'] == 'place'
                 and c['text'].endswith(('景区', '公园')) and len(c['text']) > 2
                 and not re.search(r'也有|比起|例如|沈阳的|类似', text[max(0,c['start']-6):c['start']])]
        if parks:
            return pick(parks, '景区中心词匹配实际园区而非停车场等局部')
    if re.match(r'(?:个)?点', tail):
        places = [c for c in local if c['entity_type'] == 'place' and not c.get('generic')
                  and re.match(r'[，,]?(?:这里)?(?:也)?(?:可以|有|可)', text[c['end']:c['end']+12])]
        if places:
            return pick(places, '补给点指示优先前文介绍功能的场所')
        if topic:
            return result(topic, '该点延续当前景点或补给点主题')
    if re.match(r'(?:个)?酒店', tail):
        answer = pick([c for c in previous if c['entity_type'] == 'hotel'], '酒店中心词排除附近景区')
        if answer:
            return answer
    if re.match(r'可是[^。\n]{0,8}(?:宝贝|图案)|就是[^。\n]{0,15}[“"][^”"]*碑', tail):
        answer = pick(substantive('inscription'), '图案或碑的判断句回指前述实物')
        if answer:
            return answer
    if re.match(r'(?:个)?物价', tail):
        matches = list(re.finditer(r'[^。\n]{0,12}\d+元[^。\n]{0,30}\d+元[^。\n]{0,10}', before[-180:]))
        if matches:
            return result(body_quote(matches[-1].group(), 'price_level'), '价格指示回指前述价格水平', 'price_level')

    route_hint = re.match(r'条(?:游览)?路线|条线路|条路|条道|条通道|路线|线路|登山之路|条是[^。\n]{0,15}路线|是[^。\n]{0,25}(?:路线|线路)', tail)
    if route_hint:
        old = fallback()
        if old['antecedent'] and old['antecedent']['source'] == 'current_movement_prefix':
            return old
        route = [c for c in previous if c['entity_type'] == 'route' and c['source'] in ('named_route', 'dash_route', 'defined_route')]
        choices = [c for c in local if c['source'] == 'chosen_route']
        if choices and (not route or max(c['end'] for c in choices) > max(c['end'] for c in route)):
            return pick(choices, '明确选择的当前行程优先于先前列举的路线')
        defined = [c for c in route if c['source'] == 'defined_route' and p['start'] - c['end'] <= 10]
        if defined:
            return pick(defined, '路线定义提供当前完整环线')
        if record.get('text_type') == 'official_route' and not any(c['source'] == 'dash_route' for c in route):
            return result(None, '本篇官方线路标题标识完整游览路线', 'route', text_title, 'title')
        if route:
            return pick(route, '路线指示匹配完整命名路线或连续站点')
        if record.get('text_type') == 'official_route':
            return result(None, '官方路线的主题来自文章标题', 'route', text_title, 'title')
        return result(None, '整条游览路线级指代', 'route', '本文当前讨论的路线：' + text_title, 'document')

    if re.match(r'(?:几个景点|些景点)', tail):
        match = list(re.finditer(r'[\u4e00-\u9fff]{2,8}(?:、[\u4e00-\u9fff]{2,8}){1,8}', before[-150:]))
        if match:
            value = re.split(r'有|是', match[-1].group())[-1]
            return result(body_quote(value, 'place_group'), '指向前文并列的完整地点集合', 'place_group')
    if re.match(r'(?:个)?过程', tail):
        match = list(re.finditer(r'攀登[^。\n]{3,55}(?:旅程|过程)', before[-400:]))
        if match:
            return result(body_quote(match[-1].group()), '过程指示回到前文活动过程', 'event')
    if re.match(r'作用|用途|功能', tail):
        match = list(re.finditer(r'(?:原本应该是|用来|用于)([^，。\n]{2,40})', before[-120:]))
        if match:
            return result(body_quote(match[-1].group(1), 'function'), '功能指示回到前述用途', 'function')
    if re.match(r'种美', tail):
        match = list(re.finditer(r'[^，。\n]{1,8}之美', before[-80:]))
        if match:
            return result(body_quote(match[-1].group(), 'scene'), '美的指示匹配前述景色', 'scene')
    if re.match(r'方面', tail):
        return result(None, '方面指示概括前文的问题或管理主题', 'event', '前文提及的景区问题及相关管理', 'discourse')

    # 概括前句的命题/行为；不要退化为最靠近的名词。
    prefix = before[-4:]
    if prefix.endswith(('对', '由', '如')) or re.match(r'(?:为(?:游客|大家|旅客|游人)|不一定|种自我感觉|就是以前课文)', tail):
        content = clause_before()
        if content in ('事实证明', '当然', '的确'):
            start = before.rfind(content)
            preceding = before[:start].rstrip(' ，,。！？!\n')
            content = preceding[window_start(preceding, len(preceding)):]
        if prefix.endswith(('对', '由', '如')):
            content = before[:-1].rstrip(' ，,。\n')
            content = content[window_start(content, len(content)):].strip()
        if re.match(r'种自我感觉', tail):
            content = re.split(r'[，,]', content)[-1]
        if re.match(r'就是以前课文', tail):
            persons = [c for c in local if c['entity_type'] == 'person' and c['text'].endswith(('工', '工人'))]
            if persons:
                return pick(persons, '判断句指向上文劳动者群体', 'person_group')
        if content:
            return result(body_quote(content), '命题或行为概括，保留完整前文内容', 'event')

    # 确切中心词尚未引入，按现场限定保存，不乱连到地点。
    if re.match(r'(?:两棵|一排|(?:些)?披上|座桥)', tail):
        return result(None, '首次现场指示，正文无明确前置同类对象', 'situational_deixis', '当前现场所指的' + re.split(r'[，。\n]', tail)[0], 'situation')

    # 原来的规则仍处理已明确的事件、路线和同句精确回指。
    old = fallback()
    if old['antecedent'] is None and any(s in old['reason'] for s in ('现场', '图注', '同类名词')):
        return old
    if old['antecedent'] and old['antecedent']['entity_type'] in ('event', 'route', 'place_group', 'quotation'):
        return old
    if p['text'] in ('该园', '该景区') or re.match(r'时|刻', tail):
        return old
    if re.match(r'一游', tail) and before.endswith('到'):
        places = [c for c in local if c['entity_type'] == 'place' and len(c['text']) >= 3]
        if places:
            return pick(places, '到此一游回到当前游览地点')
    if record.get('text_type') == 'official_route' and not topic and sample['pronoun_type'] == 'location':
        routes = [c for c in previous if c['entity_type'] == 'route' and c['text'].startswith('从')]
        if routes:
            route = max(routes, key=lambda c:c['end'])
            return result(route, '未进入具体景点小节时保留整条线路区域', 'area', route['text'] + '一带')
    # 官方介绍按小节组织；历史引文中的地址不是游览者当前所处位置。
    if record.get('text_type') == 'official_route' and topic and (sample['pronoun_type'] == 'location' or p['text'] == '此'):
        return result(topic, '官方景点介绍延续当前小节主题')
    is_location = (sample['pronoun_type'] == 'location'
                   or (p['text'] == '此' and (re.match(r'一游', tail) or before.endswith(('在', '于', '来'))))
                   or (p['text'] in ('这', '那') and re.match(r'[，,]', tail)))
    if is_location:
        groups = [c for c in local if c['entity_type'] == 'place'
                  and c['end'] == p['start']]
        if groups and before.rstrip().endswith(groups[-1]['text']):
            last = max(groups, key=lambda c:len(c['text']))
            left = [c for c in local if c['entity_type'] == 'place' and c['end'] < last['start']
                    and text[c['end']:last['start']] == '、']
            if left:
                first = max(left, key=lambda c:c['end'])
                return result(span(text, first['start'], last['end'], entity_type='place_group', source='colocated_places'), '当前地点是并列设施所在区域')
        facility = [c for c in local if c['entity_type'] == 'place' and c['source'] == 'located_facility'
                    and p['start'] - c['end'] <= 150]
        if facility and (not old['antecedent'] or old['antecedent']['source'] == 'pos_or_place_suffix'):
            return pick(facility, '前文明确介绍的设施位置约束当前地点')
        shops = [c for c in local if c['text'].endswith(('连锁店', '店铺')) and p['start'] - c['end'] <= 30]
        if shops and re.match(r'吃|喝|补给', tail):
            return pick(shops, '消费活动匹配邻近店铺')
        nearby = [c for c in local if c['entity_type'] == 'place' and c['source'] in ('extended_place', 'nominal_head', 'located_facility', 'quoted_place_name')
                  and len(c['text']) >= 3 and p['start'] - c['end'] < 100]
        if nearby:
            candidate = max(nearby, key=lambda c: (c['end'], len(c['text'])))
            old_ant = old['antecedent']
            if not old_ant or candidate['end'] > old_ant['end']:
                return result(candidate, '具体场所名词优先于被截断地名或普通邻近词')
    if topic and (sample['pronoun_type'] == 'location' or p['text'] == '此'):
        # 同句明示的地方优先；其他情况保留篇章当前场所，屏蔽历史引文中的城市等干扰。
        immediate = [c for c in local if c['entity_type'] == 'place' and c['end'] == p['start']]
        if immediate:
            return pick(immediate, '显式同句地点')
        old_ant = old['antecedent']
        if p['start'] - topic['end'] <= 1000 and (not old_ant or old_ant['end'] <= topic['end']):
            return result(topic, '当前景点小节主题约束')
    if record.get('text_type') == 'official_route' and not old['antecedent'] and not topic and sample['pronoun_type'] == 'location':
        return result(None, '尚未进入具体景点小节，指本篇介绍的线路区域', 'area', text_title + '沿线区域', 'title')
    return old

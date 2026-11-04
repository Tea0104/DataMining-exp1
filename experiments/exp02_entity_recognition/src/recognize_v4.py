"""使用目的地、介绍句和行程栏发现词典外景点，保留原文位置。"""
import re
from collections import Counter, defaultdict

import recognize_entities as base
import recognize_v3 as v3


# 这些是地点类别和句法线索，三个来源均不需要预先知道景点名字。
PLACE_HEADS = (
    '书院', '驿站', '古镇', '古村', '村寨', '街区', '集市', '步道', '栈道',
    '观景台', '观景平台', '游客中心', '游人中心', '遗址', '故居', '墓园', '纪念馆',
    '展览馆', '美术馆', '博物馆', '文化馆', '石窟', '瀑布', '峡谷', '溶洞', '沙滩',
    '海滩', '湿地', '温泉', '礁群', '林场', '保护区', '风景区', '景区', '营地',
    '岩', '崖', '坡', '坳', '寨', '村', '街', '巷', '滩', '岛', '屿', '礁', '溪',
    '山', '峰', '岭', '谷', '洞', '湖', '潭', '湾', '泉', '寺', '庙', '祠', '殿',
    '阁', '亭', '坊', '塔', '楼', '桥', '站', '园', '门', '馆', '酒店', '码头',
    '广场', '大坝', '水库', '碑', '石', '像', '树', '松', '瀑', '坞', '口', '台', '宫',
    '沟', '涧', '岗', '梁', '垭', '堡', '堤', '闸', '岬', '洲', '坪', '庵', '廊', '苑', '轩',
)
HEAD = '|'.join(sorted(PLACE_HEADS, key=len, reverse=True))
NAMED_PLACE = rf'[\u4e00-\u9fff·]{{1,12}}?(?:{HEAD})'
ACTIVITY = r'参观|游览|打卡|拍照|合影|休息|歇脚|等候|下车|集合|会合|停留|住宿|吃饭|喝茶|赏花|看'
RIGHT = rf'(?=$|[\s，。！？、；：,.!?;:（()）”」》→—和与及]|附近|旁边|门口|入口|出口|一带|之后|以后|前方|方向|{ACTIVITY}|时|后)'
MOTION = re.compile(
    rf'(?:抵达|到达|到访|前往|途经|路过|经过|参观|游览|造访|来到|走到|绕到|赶到|走出|穿过|沿着|(?<![等不想遇看听提])到)'
    rf'(?:了|过)?\s*(?P<name>{NAMED_PLACE}){RIGHT}'
)
LIST_ITEM = re.compile(rf'\s*[、和与及]\s*(?P<name>{NAMED_PLACE}){RIGHT}')
ORIGIN = re.compile(rf'从\s*(?P<name>{NAMED_PLACE})(?=出发|启程|步行|徒步|乘车|乘船|沿|到|至|[，、])')
LOCATION = re.compile(rf'(?<![现正存实所留])在\s*(?P<name>{NAMED_PLACE})(?=附近|旁边|门口|入口|出口|{ACTIVITY})')
INTRO = re.compile(rf'(?:^|[。！？；\n，])\s*(?P<name>{NAMED_PLACE})(?=坐落[在于]|位于|始建于|地处|旁有|附近有|是(?:一座|一处|一条))')
FIELD = re.compile(r'(?:^|[\n。；])\s*(?:景点(?:名称|包括)?|游览景点|目的地|起点|终点|途经景点)\s*[:：]\s*([^。；\n]+)')
QUOTED = r'[“「『《\"](?P<name>[\u4e00-\u9fff·]{2,16})[”」』》\"]'
NAMING = re.compile(
    rf'(?:抵达|到访|前往|途经|路过|参观|游览|景点(?:名为|叫作)?|(?:遗址|古镇|展馆|寺院|村寨|书院|步道)(?:名为|叫作|又称))\s*{QUOTED}'
)
NAME = re.compile(r'[\u4e00-\u9fff·]{2,16}')
NON_NAME = re.compile(
    r'的|了|我们|可以|需要|然后|之后|之前|对面|旁边|附近|周边|隔壁|一路|途中|走到|抵达|参观|游览|'
    r'出发|前往|路过|下车|乘坐|换乘|沿着|\A(?:新建|著名|古老|当地|附近|市内)|'
    r'这个|那个|一座|一条|一处|一些|几个|很多|所有|是否|值得|(?:再|便|就)(?:去|找|走|到|乘|看|沿|能|会)|'
    r'^\s*(?:和|及|也|再|先|往|沿|从|在|去|到|有|看|向|没|不|等|其|该|可|又)'
)
UNNAMED = set(PLACE_HEADS) | set('市区 市中心 古城 老城 山脚 山腰 半山 半山腰 山顶 山下 山上 山口 正门 后门 东门 西门 南门 北门 停车场 大门 园区 景点 观景点 自然保护区 休息 集合 拍照 午餐 早餐 晚餐 自由活动'.split())


def contextual_spans(text):
    for match in MOTION.finditer(text):
        yield *match.span('name'), 'destination'
        cursor = match.end()
        while item := LIST_ITEM.match(text, cursor):
            yield *item.span('name'), 'destination_list'
            cursor = item.end()
    for pattern, method in ((ORIGIN, 'origin'), (INTRO, 'description'), (LOCATION, 'activity_location'),
                            (NAMING, 'quoted_name')):
        for match in pattern.finditer(text):
            yield *match.span('name'), method
    for field in FIELD.finditer(text):
        for part in re.finditer(r'[^、，,→]+', field[1]):
            raw = part[0]
            name = raw.strip().strip('“”「」『』《》"')
            if NAME.fullmatch(name):
                start = field.start(1) + part.start() + raw.index(name)
                yield start, start + len(name), 'itinerary_field'


def extract(records, groups, stop, scenic):
    previous, per_doc = v3.extract(records, groups, stop, scenic)
    by_doc = defaultdict(list)
    for entity in previous:
        by_doc[entity['doc_id']].append(entity)
    blocked = v3.GENERIC | UNNAMED | stop['suffix_noise'] | stop['generic_place'] | stop['off_scenic']
    all_entities = []
    for record in records:
        doc, text = record['doc_id'], record['clean_text']
        existing = by_doc[doc]
        sentences = base.split_sentences(text)
        proposals = []
        for start, end, method in contextual_spans(text):
            name = text[start:end]
            if (name in blocked or NON_NAME.search(name) or any(word in name for word in stop['off_scenic'])
                    or re.search(r'索道|电梯|小火车|地铁|公交车|分钟|小时', name)):
                continue
            # 这些句式用于发现遗漏，已有类型和边界由原识别器决定。
            if any(start < entity['end'] and entity['start'] < end for entity in existing):
                continue
            proposals.append(base.decorate({
                'doc_id': doc, 'scenic_id': scenic, 'text': name, 'entity_type': 'POI',
                'subtype': 'contextual_place', 'start': start, 'end': end,
                'sentence_id': base.sentence_of(sentences, start), 'method': 'v4_' + method,
            }, groups))
        entities = base.resolve_overlaps([*existing, *proposals])
        all_entities.extend(entities)
        per_doc[doc].update(entities=len(entities), by_type=dict(Counter(e['entity_type'] for e in entities)))
    return all_entities, per_doc


if __name__ == '__main__':
    v3.main(version='v4', extractor=extract)

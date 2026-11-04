"""v3：在冻结的v2上增加词边界、路线/别名候选和可复用的时间交通规则。

不读取金标，不从当前文档编号或位置生成答案。输出仍以clean_text的字符偏移为准。
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import jieba.posseg
import recognize_entities as base

NUM = r'(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百几]+)'
LEFT = r'(?<![\d.零〇一二两三四五六七八九十百])'
SEPARATOR = r'\s*[-–—~～至到]{1,2}\s*'
HOUR = base.HOUR
POINT = rf'{HOUR}\s*(?:点(?:半|[一三]刻|(?:[0-5]?\d|[一二三四五六七八九十]{{1,3}})\s*分)?|时)(?:多钟|多)?'
CLOCK = base.CLOCK
FUZZY = rf'{NUM}(?:多|余)?\s*个?(?:半)?'
DURATION = rf'(?:{FUZZY}(?:{SEPARATOR}{FUZZY})?\s*(?:小时(?:半|\s*{NUM}\s*分(?:钟)?)?|分钟|秒钟?|整?天(?:\d+晚)?|日(?=有效))多?|半个?小时|[一二三四]刻钟)'
PERIODS = ('凌晨', '早上', '上午', '中午', '下午', '傍晚', '晚上', '夜里', '一早', '白天',
           '夜晚', '夜间', '清晨', '午后', '晨曦', '早高峰', '春天', '夏天', '秋天', '冬天',
           '春季', '夏季', '秋季', '冬季', '夏日', '冬日')
DAYS = ('次日早', '今天', '昨天', '明天', '明早', '当日', '当天', '次日', '双休日', '早餐后', '午餐后')
FESTIVAL = r'(?:春节(?:假期)?|中秋(?:节|假期)?|国庆(?:节|假期)?|新年|五一)'
TIME_PATTERNS = [
    (re.compile(rf'{LEFT}(?:{CLOCK}{SEPARATOR}{CLOCK}|{POINT}{SEPARATOR}{POINT}|{HOUR}{SEPARATOR}{POINT})(?!\d)'), 'clock', 'v3_clock_range'),
    (re.compile(rf'{LEFT}{CLOCK}(?![\d:：])'), 'clock', 'v3_clock'),
    (re.compile(rf'{LEFT}{POINT}(?!\d)'), 'clock', 'v3_clock'),
    (re.compile(rf'{LEFT}{DURATION}'), 'duration', 'v3_duration'),
    (re.compile(r'(?<!\d)(?:19|20)\d{2}[./-](?:1[0-2]|0?[1-9])[./-](?:3[01]|[12]\d|0?[1-9])(?:和\d{1,2}号)?(?!\d)'), 'day', 'v3_date'),
    (re.compile(rf'{LEFT}(?:{NUM}月{NUM}[日号]|\d{{1,2}}[日号])(?!有效)'), 'day', 'v3_date'),
    (re.compile(rf'{FESTIVAL}(?:的|假期)?第{NUM}天|{FESTIVAL}(?:之前|之后|前|后)?'), 'day', 'v3_calendar'),
    (re.compile(r'周[一二三四五六日天](?:[至到、和]?周[一二三四五六日天])?(?:晚上|上午|中午|下午|早上)?'), 'day', 'v3_calendar'),
    (re.compile(rf'{LEFT}\d{{1,2}}分(?=左右.{{0,6}}(?:开拔|出发|集合))'), 'clock', 'v3_minute_anchor'),
    (re.compile('|'.join(sorted(PERIODS, key=len, reverse=True))), 'period', 'v3_period'),
    (re.compile('|'.join(sorted(DAYS, key=len, reverse=True))), 'day', 'v3_day'),
    (re.compile(r'整点'), 'clock', 'v3_clock'),
]
TRANSPORT = {
    '打车': ('taxi', '出租车'), '滴滴': ('taxi', '出租车'),
    '游览车': ('shuttle', '大巴'), '旅游车': ('shuttle', '大巴'),
    '景区交通车': ('shuttle', '大巴'), '景交车': ('shuttle', '大巴'),
    '景区观光车': ('shuttle', '大巴'), '旅游大巴车': ('shuttle', '大巴'),
    '机场大巴': ('shuttle', '大巴'), '小巴车': ('shuttle', '大巴'),
    '汽车': ('mode', '汽车'), '开车': ('self_drive', '自驾'),
    '酒店接送': ('shuttle', '接送车'), '轨道交通': ('rail', '轨道交通'),
    '轻轨': ('rail', '轻轨'), '电梯': ('lift', '电梯'),
    '骑马': ('ride', '骑马'), '自行车': ('cycle', '自行车'),
    '电动车': ('electric_vehicle', '电动车'), '漫步': ('walk', '徒步'),
    '游览船': ('boat', '游船'),
}
POI_END = re.compile(r'(?:游客中心|游人中心|客运站|公园站|码头|石坊|女神像|纪念碑|雪道|广场|水库|大坝|森林浴场|世界|公园|酒店|亭|泉|岭|湾|桥|洞|谷|崖|峰|庙|寺|祠|阁|殿|坊|楼|门|站|馆|园|松|像|墓|石)$')
EXTENSION = re.compile(r'^(?:游客中心|游人中心|客运站|公园站|码头|石坊|广场|水库|大坝|索道|电梯|观光小火车|小火车|站|坊)')
GENERIC = set('游客中心 游人中心 客运站 公园站 码头 石坊 广场 水库 大坝 世界 公园 酒店 车站 宾馆 旅馆 博物馆 纪念碑 石刻 石碑 铁佛 山门 大山门 正殿 配殿 牌坊 栈道 步道 森林公园 人间 天堂 山顶 大门 寺庙 寺院 亭子 阁楼 古松 木桥 石桥 天梯 长城 出口 入口'.split())
GENERIC.update('国家森林公园 城市公园 地质公园 汽车站 火车站 高铁站 索道站 门票站 地铁站 轻轨站 广场站 始发站 换乘站 终点站 起点站 休息站 检查站 竹筏码头 女神像 高架桥 石拱桥 大雄宝殿 钟鼓楼 商务酒店 国际酒店 马拉松 后花园'.split())
ROUTE_SPLIT = re.compile(r'→|——+|--+|(?<=[\u4e00-\u9fff])—(?=[\u4e00-\u9fff])')
ALIAS = re.compile(r'(?:又称|俗称|旧称|又名|古称|其名|名为|称为|名)[“「"]([^”」"\n]{2,12})[”」"]')
HISTORY = re.compile(r'开通运营|始建|重建|创建|建于|晋升|被列入|被评为|朝代|历史|解放|定都')


def occurrences(text, word):
    start = text.find(word)
    while start >= 0:
        yield start, start + len(word)
        start = text.find(word, start + len(word))


def time_allowed(text, start, end, subtype):
    value, after = text[start:end], text[end:end + 8]
    if value.endswith('天') and re.match(r'[然下地云宫仙]', after):
        return False
    if value in ('明天', '后天') and re.match(r'[\u4e00-\u9fff]{0,3}年', after):
        return False
    if value.endswith('日') and after.startswith('游'):
        return False
    if value in ('一时', '二时', '三时') and not re.search(
            r'上午|中午|下午|晚上|凌晨|早上', text[max(0,start-4):start]):
        return False
    if value.endswith('秒') and re.match(r'变身|变成|穿越', after):
        return False
    if subtype == 'clock' and value != '整点' and not base.clock_values_valid(value):
        return False
    if re.fullmatch(r'[一二两三四五六七八九十\d]+点', value):
        if re.match(r'也|都|不|没|儿|建议|要求|意见|问题|原因', after):
            return False
        if value == '一点' and not (re.search(r'上午|中午|下午|晚上|凌晨|早上', text[max(0, start-4):start])
                                    or re.match(r'左右|钟|前|后|时|开始|出发|到达|入园', after)):
            return False
    if subtype == 'day' and re.search(r'[年月日号]|\d+[./-]\d+', value):
        if HISTORY.search(text[max(0, start - 18):end + 12]):
            return False
    return True


def extract(records, groups, stop, scenic):
    old, _ = base.extract(records, 'v2', groups, stop, scenic)
    by_doc = {}
    for entity in old:
        by_doc.setdefault(entity['doc_id'], []).append(entity)
    tokenizer = base.register_lexicon(groups)
    pos = jieba.posseg.POSTokenizer(tokenizer)
    all_entities, per_doc = [], {}
    for record in records:
        text, doc = record['clean_text'], record['doc_id']
        sentences = base.split_sentences(text)
        candidates = [e for e in by_doc.get(doc, []) if e['entity_type'] != 'TIME'
                      or time_allowed(text, e['start'], e['end'], e['subtype'])]

        def add(start, end, kind, subtype, method, **extra):
            word = text[start:end]
            if kind == 'TRANSPORT' and re.match(r'换乘|乘坐|搭乘|改乘', word):
                return  # 动作词不属于线路名称；独立的交通名词候选仍保留。
            if kind == 'POI' and (word in GENERIC or word in stop['suffix_noise']
                                  or word in stop['generic_place'] or word in stop['off_scenic']):
                return
            if kind in ('POI', 'TRANSPORT') and any(w in word for w in stop['off_scenic']):
                return
            if method.startswith('v3_pos') and (re.match(r'因|为|从|关上|可以', word)
                    or (word.endswith('洞') and text[end:end+1]=='幽')
                    or re.search(r'题联|上联曰|下联曰', text[max(0,start-20):start])):
                return
            candidates.append({'doc_id': doc, 'scenic_id': scenic, 'text': word,
                               'entity_type': kind, 'subtype': subtype, 'start': start, 'end': end,
                               'sentence_id': base.sentence_of(sentences, start),
                               'method': method, **extra})

        # 字符串词典匹配不再受单次分词的切分边界限制。
        for kind, group in (('POI', 'poi'), ('TRANSPORT', 'transport'), ('TIME', 'time')):
            for word, entry in groups[group].items():
                for start, end in occurrences(text, word):
                    if not base.context_allows(entry, text, start, end):
                        continue
                    add(start, end, kind, entry.get('subtype', 'other'), 'v3_dictionary')
                    if kind == 'POI':
                        extension = EXTENSION.match(text[end:])
                        if extension:
                            suffix = extension.group()
                            transport = suffix in ('索道', '电梯', '观光小火车', '小火车')
                            add(start, end + len(suffix), 'TRANSPORT' if transport else 'POI',
                                {'索道':'cableway', '电梯':'lift', '观光小火车':'train', '小火车':'train'}.get(suffix,'facility'),
                                'v3_name_extension')
        for word, (subtype, canonical) in TRANSPORT.items():
            for start, end in occurrences(text, word):
                if word in ('轻轨','轨道交通') and re.match(r'(?:线路|站|[\u4e00-\u9fff]{1,6}站)',text[end:]):
                    continue
                if word == '电梯' and re.search(r'与[^，。；;\n]{0,12}$',text[max(0,start-16):start]) and re.match(r'等并称',text[end:]):
                    continue
                add(start, end, 'TRANSPORT', subtype, 'v3_transport', canonical=canonical)
        for match in re.finditer(r'(?:地铁|轻轨|轨道交通)\s*[\d一二三四五六七八九十]+号线', text):
            add(match.start(), match.end(), 'TRANSPORT', 'rail', 'v3_rail_line')
        for pattern, subtype, method in TIME_PATTERNS:
            for match in pattern.finditer(text):
                if time_allowed(text, match.start(), match.end(), subtype):
                    add(match.start(), match.end(), 'TIME', subtype, method)

        # 箭头链路的节点是高置信候选；逐节点解析，不把相邻两个词典实体粘成新名字。
        offset = 0
        for line in text.splitlines(keepends=True):
            separators = list(ROUTE_SPLIT.finditer(line))
            is_route = ('→' in line or ('路线' in line or '线路' in line or '经过' in line)
                        or (len(separators)>=2 and not re.search(r'[“”"，。]',line)))
            if separators and is_route:
                for part in re.finditer(r'[^→\n]+', line):
                    # 再按长破折号切分，保留原始偏移。
                    begin = 0
                    for delim in list(ROUTE_SPLIT.finditer(part.group())) + [None]:
                        finish = delim.start() if delim else len(part.group())
                        chunk = part.group()[begin:finish]
                        clean = re.sub(r'^[\s\d、.]*|[\s。；;]+$', '', chunk)
                        clean = re.sub(r'^(?:路线[一二三四五六七八九十]*[：:]|徒步至|乘坐|从|终点)', '', clean)
                        clean = re.sub(r'^.*?(?:路线是|线路是|路线[：:]|线路[：:]|中途设|依次经过)', '', clean)
                        clean = re.split(r'[（(]|\s+宿|\s+/', clean)[0].strip()
                        clean = re.sub(r'^(?:.*?至)(?=[\u4e00-\u9fff]{2,12}$)', '', clean)
                        clean = re.sub(r'^终点|站点$|下车$', '', clean)
                        if 2 <= len(clean) <= 12 and re.fullmatch(r'[\u4e00-\u9fff·]+', clean):
                            start = offset + part.start() + begin + chunk.find(clean)
                            end = start + len(clean)
                            inside = [e for e in candidates if e['entity_type']=='POI'
                                      and start <= e['start'] and e['end'] <= end]
                            covered = sum(e['end']-e['start'] for e in base.resolve_overlaps(inside))
                            if not (len(inside) >= 2 and covered >= len(clean)) and not re.search(
                                    r'我们|可以|选择|决定|就是|需要|这|那|一个|有些|的|是',clean):
                                if not re.search(r'索道|天梯|电梯|小火车|小时', clean):
                                    add(start, end, 'POI', 'route_node', 'v3_route_node')
                        begin = delim.end() if delim else finish
            offset += len(line)

        # 在词性和地名后缀双重约束下，补充分词后缀被切开的具名设施。
        tokens, offset = [], 0
        for token in pos.cut(text):
            tokens.append((token.word, token.flag, offset, offset + len(token.word)))
            offset += len(token.word)
        for index, (word, flag, start, end) in enumerate(tokens):
            if 3 <= len(word) <= 10 and flag.startswith('n') and POI_END.search(word):
                add(start, end, 'POI', 'suffix', 'v3_pos_suffix')
            if word in ('站', '阁', '亭', '泉', '码头', '女神像', '酒店') and index:
                previous, tag, pstart, pend = tokens[index-1]
                if pend == start and tag.startswith('n') and 2 <= len(previous) <= 6:
                    add(pstart, end, 'POI', 'facility', 'v3_pos_compound')
            if word in ('索道', '天梯', '电梯', '小火车') and index:
                previous, tag, pstart, pend = tokens[index-1]
                if pend == start and tag in ('ns','nr','nz') and 2 <= len(previous) <= 6 and previous not in (
                        '景区', '酒店', '宾馆', '高山', '山顶') and previous not in stop['generic_place'] and not previous.startswith('从'):
                    add(pstart, end, 'TRANSPORT', 'cableway' if word=='索道' else 'lift', 'v3_named_transport')
            if flag == 'ns' and 2 <= len(word) <= 4:
                line = re.match(r'(?:轻轨|地铁|轨道交通)\s*[\d一二三四五六七八九十]+号线', text[end:])
                if line:
                    add(start, end+len(line.group()), 'TRANSPORT', 'rail', 'v3_city_rail_line')
            if word == '酒店' and index >= 2:
                first, first_tag, first_start, first_end = tokens[index-2]
                middle, middle_tag, middle_start, middle_end = tokens[index-1]
                if first_tag in ('nr','ns','nz') and middle_tag.startswith('n') and first_end==middle_start and middle_end==start:
                    add(first_start,end,'POI','facility','v3_proper_hotel')
        for topic in stop['generic_place']:
            if len(topic) < 2:
                continue
            for match in re.finditer(re.escape(topic)+r'(?:气象站|大坝|公园站)',text):
                add(match.start(),match.end(),'POI','facility','v3_topic_facility')
        for match in re.finditer(r'以([\u4e00-\u9fff]{2,8}像)为中心',text):
            add(match.start(1),match.end(1),'POI','landmark','v3_named_statue')
        for match in re.finditer(r'(?:建|额书|额题|题刻|叫)[“「"]([\u4e00-\u9fff]{2,12})[”」"]',text):
            name=match.group(1)
            if POI_END.search(name):
                add(match.start(1),match.end(1),'POI','landmark','v3_named_quote')
        for match in ALIAS.finditer(text):
            name = match.group(1)
            before = text[max(0, match.start()-45):match.start()]
            if re.fullmatch(r'[\u4e00-\u9fff]{2,12}', name) and re.search(
                    r'峰|庙|寺|洞|亭|楼|松|石|景区|后石坞|公园|瀑|湾|岗|碑', before):
                if not re.search(r'神女|玉帝|元君又称|俗称为|奶奶', before):
                    add(match.start(1), match.end(1), 'POI', 'alias', 'v3_alias')

        entities = base.resolve_overlaps(candidates)
        decorated = []
        for entity in entities:
            canonical = entity.get('canonical')
            item = base.decorate(entity, groups)
            if canonical:
                item['canonical'] = canonical
            assert text[item['start']:item['end']] == item['text']
            decorated.append(item)
        all_entities.extend(decorated)
        per_doc[doc] = {'chars': len(text), 'sentences': len(sentences), 'entities': len(decorated),
                        'by_type': dict(Counter(e['entity_type'] for e in decorated))}
    return all_entities, per_doc


def main(argv=None, *, version='v3', extractor=extract):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=base.DEFAULT_INPUT)
    parser.add_argument('--scenic', nargs='+', choices=(*base.SCENICS, 'all') if version == 'v3' else None,
                        default=['all'])
    parser.add_argument('--outputs', type=Path, default=base.SRC.parent / 'outputs')
    args = parser.parse_args(argv)
    records = base.load_json(args.input)
    available = tuple(dict.fromkeys(record['scenic_id'] for record in records))
    defaults = base.SCENICS if version == 'v3' else available
    selected = defaults if 'all' in args.scenic else tuple(dict.fromkeys(args.scenic))
    if not selected or any(scenic not in available or not re.fullmatch(r'[\w-]+', scenic) for scenic in selected):
        parser.error('输入数据须包含所选景区，scenic_id 仅使用字母、数字、下划线或短横线')
    args.outputs.mkdir(parents=True, exist_ok=True)
    lexicon = base.load_json(base.CONFIG / 'lexicon.json')
    stopwords = base.load_json(base.CONFIG / 'stopwords.json')
    summary = {}
    for scenic in selected:
        groups = base.build_lexicon(lexicon, scenic)
        scoped = [record for record in records if record['scenic_id'] == scenic]
        stop = base.build_stopwords(stopwords, scenic)
        if version != 'v3' and scenic not in base.SCENICS:
            # 旧语料的外部地点在新景区可能正是目标地点。
            stop['off_scenic'].clear()
        entities, per_doc = extractor(scoped, groups, stop, scenic)
        stats = base.summarize(entities, per_doc, version, scenic)
        for name, payload in [(f'entities_{scenic}_{version}.json', entities), (f'stats_{scenic}_{version}.json', stats)]:
            (args.outputs / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
        rows = base.write_frequency(entities, args.outputs, version, scenic)
        chart = base.plot_frequency(rows, args.outputs, version, scenic)
        summary[scenic] = {'name': base.SCENIC_CN.get(scenic, scenic), 'docs': len(scoped),
                           'mentions': len(entities), 'by_type': stats['by_type'], 'chart': chart.name}
        print(scenic, len(entities), stats['by_type'])
    payload = {'version': version, 'scenics': summary, 'totals': {
        'docs': sum(s['docs'] for s in summary.values()),
        'mentions': sum(s['mentions'] for s in summary.values()),
        'by_type': {t: sum(s['by_type'][t] for s in summary.values()) for t in base.TYPE_ORDER}}}
    (args.outputs / f'stats_all_{version}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

"""v1 最近名词基线；v2 类型、距离、站点语境和拒绝消解规则。运行时不读取标注。"""
import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

import jieba
import jieba.posseg as posseg

from common import DATASET, OUTPUTS, ROOT, load_records, read_json, sentences, span, validate_span, write_json

PERSON = ('女郎', '女儿', '姑娘', '小女孩', '小姐姐', '女子', '爸爸', '老人', '儿童',
          '游客', '学生', '老板', '乘客', '司机', '摄影师', '售票员', '工作人员')
FEMALE = {'女郎', '女儿', '姑娘', '小女孩', '小姐姐', '女子'}
ANIMAL = ('大猴子', '猴子', '小松鼠', '花鼠', '鸬鹚', '东北虎', '非洲狮', '棕熊', '梅花鹿', '鸟类')
PLACE_NOUNS = ('商铺', '路边商铺', '公园入口', '入口', '荷花池', '广场', '公园', '寺庙',
               '森林', '湖滨', '码头', '车站', '站点', '庙宇', '景区', '景区本体', '桥')
OBJECTS = ('石刻', '摩崖石刻', '人工湖泊', '题刻', '气息', '香火味', '游览图', '栗子', '塑料袋')
PLACE_END = ('公园', '景区', '寺', '庙', '门', '阁', '峰', '湖', '潭', '坊', '桥', '广场', '站', '码头', '入口', '商铺', '花池', '园')


def nominal_candidates(record, entities):
    text = record['clean_text']
    tokenizer = jieba.Tokenizer()
    for word in (*PERSON, *ANIMAL, *PLACE_NOUNS, *OBJECTS):
        tokenizer.add_word(word, freq=20000)
    for entity in entities:
        validate_span(text, entity)
        tokenizer.add_word(entity['text'], freq=20000)
    candidates = {}

    def add(start, end, kind, source, **extra):
        key = (start, end, kind)
        candidates[key] = span(text, start, end, entity_type=kind, source=source, **extra)

    offset = 0
    for word, flag in posseg.POSTokenizer(tokenizer).cut(text):
        start, offset = offset, offset + len(word)
        if text[start:offset] != word:
            raise ValueError('分词偏移发生变化')
        if word in PERSON or flag == 'nr':
            add(start, offset, 'person', 'pos_or_semantic_lexicon',
                gender='female' if word in FEMALE else 'unspecified')
        elif word in ANIMAL:
            add(start, offset, 'animal', 'semantic_lexicon')
        elif word in PLACE_NOUNS or word.endswith(PLACE_END) or flag == 'ns':
            if len(word) > 1:
                add(start, offset, 'place', 'pos_or_place_suffix', generic=word in PLACE_NOUNS)
        elif flag.startswith('n') and len(word) > 1:
            add(start, offset, 'object', 'pos_noun')
    # 精确的多字名词覆盖词典漏切；仍只产生原文实际出现的候选。
    for word in (*PERSON, *ANIMAL, *PLACE_NOUNS, *OBJECTS):
        for match in re.finditer(re.escape(word), text):
            kind = ('person' if word in PERSON else 'animal' if word in ANIMAL else
                    'place' if word in PLACE_NOUNS else 'object')
            add(match.start(), match.end(), kind, 'semantic_lexicon',
                gender='female' if word in FEMALE else 'unspecified', generic=word in PLACE_NOUNS)
    for entity in entities:
        if entity['entity_type'] in ('POI', 'TIME'):
            add(entity['start'], entity['end'], 'place' if entity['entity_type'] == 'POI' else 'time',
                'exp02_v2', generic=entity.get('granularity') == 'generic')
    # 实验二有意排除景区本体；共指任务仍允许它作为先行词。
    for match in re.finditer(r'[\u4e00-\u9fff]{2,12}(?:国家森林公园|国家级风景名胜区)', text):
        word = re.split('[的在于暨]', match.group())[-1]
        if len(word) >= 5:
            add(match.end() - len(word), match.end(), 'place', 'scenic_full_name')
    for match in re.finditer(r'第[一二三四五六七八九十\d]+站[：:]\s*([^\n（(。]+)', text):
        name = match.group(1).strip()
        start = match.start(1) + len(match.group(1)) - len(match.group(1).lstrip())
        add(start, start + len(name), 'place', 'station_heading')
    for match in re.finditer(r'(?:凌晨|早上|上午|中午|下午|晚上)?[零一二两三四五六七八九十\d]+点(?:半|[\d一二三四五六七八九十]+分)?', text):
        add(match.start(), match.end(), 'time', 'explicit_time')
    humans = '|'.join(PERSON)
    for match in re.finditer(rf'(?:{humans})[^。！？；;\n（）()]{{0,12}}?(?:和|、|，|,)[^。！？；;\n（）()]{{0,8}}?(?:{humans})(?:\d+岁(?:以上|以下))?', text):
        add(match.start(), match.end(), 'person', 'coordinated_people', gender='unspecified', plural=True)
    return sorted(candidates.values(), key=lambda c: (c['start'], c['end'], c['entity_type']))


def non_anaphoric_reason(sample, text):
    p = sample['pronoun']
    tail = text[p['end']:p['end'] + 16]
    if re.match(r'句[“"「]', tail):
        return '后指引语，不存在前文先行词'
    if re.match(r'年', tail):
        return '泛指时间范围，不链接景点或物体'
    if re.match(r'(?:是)?[^。\n]{0,8}游览图', tail):
        return '图像指示，正文不足以确认先行词'
    return None


def choose(sample, text, candidates, version, max_distance=400):
    p = sample['pronoun']
    previous = [c for c in candidates if c['end'] <= p['start'] and p['start'] - c['end'] <= max_distance]
    if version == 'v1':
        nouns = [c for c in previous if c['entity_type'] != 'time']
        if nouns:
            return max(nouns, key=lambda c: (c['end'], c['end'] - c['start'])), '最近名词基线', []
        return None, '窗口内没有名词候选', []
    if reason := non_anaphoric_reason(sample, text):
        return None, reason, []
    kind = sample['pronoun_type']
    tail = text[p['end']:p['end'] + 30]
    head = next((w for w in (*OBJECTS, *PLACE_NOUNS) if re.match(r'(?:[座个股种块条段片一几古老的]{0,6})' + re.escape(w), tail)), None)
    if not head and kind == 'demonstrative' and re.match(r'(?:[座个股种块条段片一几]|[^，。；\n]{0,6}的)', tail):
        noun_hits = [(tail.find(w), -len(w), w) for w in (*OBJECTS, *PLACE_NOUNS)
                     if 0 <= tail.find(w) < 12]
        if noun_hits:
            head = min(noun_hits)[2]
    if kind == 'person':
        allowed = {'person'}
    elif kind == 'location':
        allowed = {'place'}
    elif kind == 'thing_or_animal':
        animals = [c for c in previous if c['entity_type'] == 'animal' and p['start'] - c['end'] < 180]
        allowed = {'animal'} if animals else {'place', 'object'}
        if re.match(r'是[^。\n]{0,12}(?:森林|公园|景区)', tail):
            allowed = {'place'}
    elif head in OBJECTS:
        allowed = {'object'}
    elif head in PLACE_NOUNS or re.match(r'(?:座|条|段)', tail):
        allowed = {'place'}
    elif re.match(r'(?:时|刻|一瞬间|一刻)', tail):
        allowed = {'time'}
    else:
        allowed = {'place', 'object'}
    compatible = [c for c in previous if c['entity_type'] in allowed]
    if sample['pronoun']['text'] in ('她', '她们'):
        compatible = [c for c in compatible if c.get('gender') == 'female']
    if head:
        exact_heads = [c for c in compatible if c['text'].endswith(head)]
        if exact_heads:
            compatible = exact_heads
        elif head in ('商铺', '路边商铺', '气息', '香火味', '游览图', '桥'):
            return None, '首次引入的物体或现场指示，前文无同类候选', []
    if not compatible:
        return None, '窗口内没有符合代词类型的先行词，保留未消解', []
    headings = [c for c in previous if c['source'] == 'station_heading']
    current_heading = max(headings, key=lambda c: c['end'])['text'] if headings else None
    ranked = []
    for candidate in compatible:
        distance = p['start'] - candidate['end']
        score = 50 - distance / 8
        reasons = ['类型相容', f'距离{distance}字']
        if candidate['start'] >= sample['sentence']['start']:
            score += 15
            reasons.append('同句')
        if candidate.get('generic'):
            score -= 12
        if (candidate['source'] in ('exp02_v2', 'context_named_place')
                or candidate.get('type_evidence') == 'exp02_v2') and candidate['entity_type'] == 'place':
            score += 12
            reasons.append('实验二具名景点候选' if candidate['source'] == 'exp02_v2' else '扩展具名地点候选')
        if candidate['text'] == current_heading:
            score += 18
            reasons.append('站点标题提供场景')
        if distance <= 1 and not text[candidate['end']:p['start']].strip():
            score += 40
            reasons.append('紧邻显式地点或名词')
        if sample['pronoun']['text'].endswith('们') and candidate.get('plural'):
            score += 25
            reasons.append('复数人群')
        if head and candidate['text'].endswith(head):
            score += 30
            reasons.append('名词中心词一致')
        preceding = text[max(0, candidate['start'] - 5):candidate['start']]
        following = text[candidate['end']:candidate['end'] + 8]
        if re.search(r'(?:到达|走到|在|位于)$', preceding):
            score += 10
            reasons.append('当前位置线索')
        if re.match(r'是|位于|有', following):
            score += 6
        if '方向' in following or re.search(r'离$', preceding):
            score -= 18
            reasons.append('方向/距离提及降权')
        ranked.append({'candidate': candidate, 'score': round(score, 3), 'reasons': reasons})
    ranked.sort(key=lambda r: (r['score'], r['candidate']['end'], len(r['candidate']['text'])), reverse=True)
    return ranked[0]['candidate'], '；'.join(ranked[0]['reasons']), ranked[:5]


def render_annotations(text, predictions):
    annotated = text
    for prediction in sorted(predictions, key=lambda p: p['pronoun']['start'], reverse=True):
        target = prediction.get('referent', {}).get('description')
        if not target and prediction['antecedent'] is not None:
            target = prediction['antecedent']['text']
        if target:
            end = prediction['pronoun']['end']
            annotated = annotated[:end] + f"〔指：{target}〕" + annotated[end:]
    return annotated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--samples', type=Path, default=OUTPUTS / 'samples.json')
    parser.add_argument('--entities', type=Path, default=ROOT / 'experiments/exp02_entity_recognition/outputs')
    parser.add_argument('--version', choices=('v1', 'v2', 'v3', 'v4'), default='v4')
    parser.add_argument('--max-distance', type=int, default=400)
    parser.add_argument('--outputs', type=Path, default=OUTPUTS)
    args = parser.parse_args()
    if args.max_distance <= 0:
        parser.error('--max-distance 必须大于零')
    records = {r['doc_id']: r for r in load_records(args.input)}
    samples = read_json(args.samples)
    if len({s['sample_id'] for s in samples}) != len(samples):
        raise ValueError('存在重复 sample_id')
    entities = defaultdict(list)
    files = list(args.entities.glob('entities_*_v2.json'))
    if not files:
        raise FileNotFoundError(f'实验二实体不存在: {args.entities}')
    for path in files:
        for entity in read_json(path):
            entities[entity['doc_id']].append(entity)
    predictions, candidates_by_doc, baseline_candidates = [], {}, {}
    for sample in samples:
        doc = sample['doc_id']
        text = records[doc]['clean_text']
        validate_span(text, sample['pronoun'])
        if doc not in candidates_by_doc:
            candidates_by_doc[doc] = nominal_candidates(records[doc], entities[doc])
            if args.version in ('v3', 'v4'):
                from context_rules import expand_candidates
                candidates_by_doc[doc] = expand_candidates(text, candidates_by_doc[doc])
            if args.version == 'v4':
                from discourse import expand_discourse
                baseline_candidates[doc] = candidates_by_doc[doc]
                candidates_by_doc[doc] = expand_discourse(records[doc], candidates_by_doc[doc])
        referent = None
        if args.version in ('v3', 'v4'):
            from context_rules import choose_context
            if args.version == 'v4':
                from discourse import infer
                def fallback():
                    a, r, ranking = choose_context(sample, text, baseline_candidates[doc], choose, args.max_distance)
                    return {'antecedent': a, 'reason': r, 'ranked_candidates': ranking}
                decision = infer(records[doc], sample, candidates_by_doc[doc], fallback)
                ant, reason, ranked = decision['antecedent'], decision['reason'], decision['ranked_candidates']
                referent = decision.get('referent')
            else:
                ant, reason, ranked = choose_context(sample, text, candidates_by_doc[doc], choose, args.max_distance)
        else:
            ant, reason, ranked = choose(sample, text, candidates_by_doc[doc], args.version, args.max_distance)
        if ant:
            validate_span(text, ant)
            if ant['end'] > sample['pronoun']['start']:
                raise ValueError('先行词不得取自代词后文')
        predictions.append({
            'sample_id': sample['sample_id'], 'doc_id': doc, 'scenic_id': sample['scenic_id'],
            'source_url': sample['source_url'], 'pronoun': sample['pronoun'],
            'pronoun_type': sample['pronoun_type'], 'version': args.version,
            'resolution_status': 'resolved' if ant else 'unresolved',
            'antecedent': ant, 'reason': reason, 'ranked_candidates': ranked,
        })
        if referent:
            predictions[-1]['referent'] = referent
    write_json(args.outputs / f'predictions_{args.version}.json', predictions)
    write_json(args.outputs / f'links_{args.version}.json', [
        {'doc_id': p['doc_id'], 'source_url': p['source_url'], 'subject': p['pronoun'],
         'predicate': 'refers_to', 'object': p['antecedent'], 'sample_id': p['sample_id']}
        for p in predictions if p['antecedent']])
    write_json(args.outputs / f'annotated_texts_{args.version}.json', [
        {'doc_id': doc, 'source_url': records[doc].get('source_url'), 'original_text': records[doc]['clean_text'],
         'annotated_text': render_annotations(records[doc]['clean_text'], [p for p in predictions if p['doc_id'] == doc]),
         'offsets_refer_to': 'original_text; annotated_text 的位置不可用于原文证据'}
        for doc in dict.fromkeys(s['doc_id'] for s in samples)])
    write_json(args.outputs / f'candidates_{args.version}.json', candidates_by_doc)
    print(f"{args.version}: {len(predictions)} samples; {sum(p['antecedent'] is not None for p in predictions)} linked")


if __name__ == '__main__':
    main()

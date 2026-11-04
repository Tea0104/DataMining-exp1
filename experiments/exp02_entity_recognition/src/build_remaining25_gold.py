"""将助手逐篇阅读原文整理的名称清单导出为参考金标；不读取预测实体。"""
import hashlib
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
OUTPUTS = BASE / 'outputs'
LABELS = BASE / 'annotations/remaining25_labels.json'
TYPES = ('POI', 'TRANSPORT', 'TIME')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def main():
    records = {r['doc_id']: r for r in read(ROOT / 'data/processed/full/selected_v2/dataset.json')}
    original_scope = {d for scenic in ('TAISHAN', 'WULINGYUAN', 'JINGYUETAN')
                      for d in read(OUTPUTS / f'gold_{scenic}.json')['doc_scope']}
    labels = read(LABELS)
    assert set(labels) == set(records) - original_scope and len(labels) == 25
    items, nested_only = [], []
    for doc_id, groups in labels.items():
        text = records[doc_id]['clean_text']
        assert set(groups) == set(TYPES)
        for entity_type, names in groups.items():
            assert len(names) == len(set(names)), (doc_id, entity_type, 'duplicate label')
            all_spans = []
            for name in names:
                start = text.find(name)
                assert name and start >= 0, (doc_id, entity_type, name)
                while start >= 0:
                    all_spans.append((name, start, start + len(name)))
                    start = text.find(name, start + len(name))
            for name in names:
                # 同类型长名优先。短名若只出现在已标长名内部，不再单列。
                eligible = [(s, e) for n, s, e in all_spans if n == name and not any(
                    n2 != name and s2 <= s and e <= e2 and e2 - s2 > e - s
                    for n2, s2, e2 in all_spans)]
                if not eligible:
                    nested_only.append({'doc_id': doc_id, 'entity_type': entity_type, 'text': name})
                    continue
                start, end = eligible[-1]
                items.append({'doc_id': doc_id, 'entity_type': entity_type, 'text': name,
                              'start': start, 'end': end,
                              'source_url': records[doc_id].get('source_url'),
                              'context': text[max(0, start - 30):end + 30]})
    # 与现有评价保持一致：仅空白不同的名称算同一项，保留原文变体证据。
    unique = {}
    for item in items:
        key = (item['doc_id'], item['entity_type'], ''.join(item['text'].split()))
        if key in unique:
            unique[key].setdefault('surface_variants', []).append(item)
        else:
            unique[key] = item
    items = list(unique.values())
    metadata = {
        'schema_version': '3', 'annotation_date': '2026-11-02',
        'annotated_by': 'AI 助手逐篇阅读 clean_text 标注；未经用户人工复核',
        'human_reviewed': False, 'evaluation_level': 'document_type_surface_name',
        'granularity': '名称级；每项附一处原文位置证据，不是所有出现次数的逐次金标。',
        'annotation_input_sha256': hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        'source_text_sha256': {d: hashlib.sha256(records[d]['clean_text'].encode('utf-8')).hexdigest()
                               for d in labels},
        'notes': [
            '在查看本轮预测对照结果之前保存名称清单；导出脚本不读取 entities、词典或识别规则。',
            '这些文章已用于此前词典开发，不是未见过的独立测试集；助手标注可能存在遗漏或歧义。',
            '名称严格按原文匹配，全称、简称、别名不自动合并；同类型长名包含的短名不重复计。',
            '景区主题名、外部地点、未具名通名、人物、神灵、历史年份和地质年龄不标。',
            '具名内部设施、地标碑刻、别名及直接接入的具名车站和住宿节点计POI；连锁品牌无具体门店名不单列。',
            '明确的交通同义表达（如打车、骑马、漫步）和具名交通线路按原词标；娱乐项目不当交通。',
            '与游览有关的日期、季节、时段、节日、时刻、时长和有效期计TIME；历史年代和单独单位不计。',
            '早餐后、午餐后等是时间锚点；作为餐食或活动的早餐、演出名称不单独标为时间。',
            '原文疑似错名仍按表面形式标注（如金鞭溪索道、天外天客运站），不证明该设施真实存在。'],
    }
    write(OUTPUTS / 'gold_remaining25.json', {
        **metadata, 'doc_scope': list(labels), 'items': items,
        'nested_only_excluded': nested_only})
    for scenic in ('TAISHAN', 'WULINGYUAN', 'JINGYUETAN'):
        docs = [d for d in labels if records[d]['scenic_id'] == scenic]
        write(OUTPUTS / f'gold_remaining25_{scenic}.json', {
            **metadata, 'scenic_id': scenic, 'doc_scope': docs,
            'source_text_sha256': {d: metadata['source_text_sha256'][d] for d in docs},
            'items': [item for item in items if item['doc_id'] in docs]})
    write(OUTPUTS / 'gold_remaining25_manifest.json', {
        'annotation_status': 'assistant_only_not_human_reviewed',
        'documents': len(labels), 'items': len(items),
        'by_type': dict(Counter(item['entity_type'] for item in items)),
        'by_doc': {d: sum(item['doc_id'] == d for item in items) for d in labels},
        'original5_doc_scope': sorted(original_scope), 'remaining25_doc_scope': list(labels),
        'labels_sha256': metadata['annotation_input_sha256'],
        'gold_sha256': hashlib.sha256((OUTPUTS / 'gold_remaining25.json').read_bytes()).hexdigest(),
        'nested_only_excluded': nested_only})
    print(f'Frozen reference: {len(labels)} documents, {len(items)} names; '
          f'{len(nested_only)} nested-only names excluded. No predictions read.')


if __name__ == '__main__':
    main()

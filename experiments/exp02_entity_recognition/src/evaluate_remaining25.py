"""评价新增25篇助手参考金标，单独保存结果，不覆盖原5篇评价。"""
import argparse
import hashlib
from collections import Counter
from pathlib import Path

from evaluate import OUTPUTS, TYPES, evaluate, gold_set, load_json, pred_set, prf

ROOT = Path(__file__).resolve().parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('v1', 'v2', 'v3', 'v4', 'v5'), default='v2')
    args = parser.parse_args()
    source = ROOT / 'data/processed/full/selected_v2/dataset.json'
    records = {r['doc_id']: r for r in load_json(source)}
    gold_path = OUTPUTS / 'gold_remaining25.json'
    manifest = load_json(OUTPUTS / 'gold_remaining25_manifest.json')
    assert digest(gold_path) == manifest['gold_sha256'], '参考金标与保存的清单不一致'
    labels_path = OUTPUTS.parent / 'annotations/remaining25_labels.json'
    assert digest(labels_path) == manifest['labels_sha256'], '名称清单已变化，需重新导出金标'
    gold = load_json(gold_path)
    scope = set(gold['doc_scope'])
    old_scope = set(manifest['original5_doc_scope'])
    assert len(scope) == 25 and not scope & old_scope
    assert scope | old_scope == set(records) and len(old_scope) == 5
    for doc_id, expected in gold['source_text_sha256'].items():
        assert hashlib.sha256(records[doc_id]['clean_text'].encode('utf-8')).hexdigest() == expected
    truth = gold_set(gold)
    assert len(truth) == len(gold['items']) == manifest['items']
    for item in gold['items']:
        assert records[item['doc_id']]['clean_text'][item['start']:item['end']] == item['text']
    predictions = []
    prediction_files = {}
    results = []
    for scenic in ('TAISHAN', 'WULINGYUAN', 'JINGYUETAN'):
        path = OUTPUTS / f'entities_{scenic}_{args.version}.json'
        prediction_files[path.name] = digest(path)
        entities = load_json(path)
        predictions.extend(e for e in entities if e['doc_id'] in scope)
        result = evaluate(args.version, scenic, OUTPUTS / f'gold_remaining25_{scenic}.json')
        # 分景区文件必须和已保存的合并金标完全一致，避免使用陈旧的子文件。
        expected = {x for x in truth if records[x[0]]['scenic_id'] == scenic}
        assert gold_set(load_json(OUTPUTS / result['gold_file'])) == expected
        results.append(result)
    pred = pred_set(predictions)
    by_type = {t: prf({x for x in pred if x[1] == t}, {x for x in truth if x[1] == t}) for t in TYPES}
    by_doc = [{
        'doc_id': doc_id, 'scenic_id': records[doc_id]['scenic_id'],
        **prf({x for x in pred if x[0] == doc_id}, {x for x in truth if x[0] == doc_id})}
        for doc_id in gold['doc_scope']]

    def details(keys):
        output = []
        for doc_id, entity_type, name in sorted(keys):
            text = records[doc_id]['clean_text']
            # norm() 会删除空白，所以查找定位时优先使用原始表面形式。
            raw_names = [i['text'] for i in gold['items'] if i['doc_id'] == doc_id
                         and i['entity_type'] == entity_type and ''.join(i['text'].split()) == name]
            raw_names += [e['text'] for e in predictions if e['doc_id'] == doc_id
                          and e['entity_type'] == entity_type and ''.join(e['text'].split()) == name]
            raw = raw_names[0]
            start = text.find(raw)
            assert start >= 0
            output.append({'doc_id': doc_id, 'entity_type': entity_type, 'text': raw,
                           'start': start, 'end': start + len(raw),
                           'context': text[max(0, start - 35):start + len(raw) + 35]})
        return output

    payload = {
        'version': args.version, 'evaluation_scope': 'remaining25', 'documents': len(scope),
        'evaluation_level': 'document_type_surface_name',
        'annotation_status': 'assistant_only_not_human_reviewed',
        'gold_items': len(truth), 'prediction_names': len(pred),
        'prediction_mentions': len(predictions),
        'overall': prf(pred, truth), 'by_type': by_type, 'by_scenic': results, 'by_doc': by_doc,
        'false_negative': details(truth - pred), 'predicted_only': details(pred - truth),
        'reference_sha256': digest(gold_path), 'prediction_files_sha256': prediction_files,
        'limitations': [
            '参考金标为助手逐篇阅读原文标注，按用户要求不经人工复核；可能存在遗漏和判断偏差。',
            '当前词表此前已在同一30篇语料上开发；本结果不代表新数据集的独立泛化性能。',
            '名称严格匹配，只忽略空白；同义词、别名、短片段不自动判为命中。',
            '召回率为 TP/(TP+FN)，不是处理篇数覆盖率，也不是每次实体出现边界的准确率。',
            ({'v3': 'v3规则参考本批漏识类型开发，因此这是开发集上的迭代比较，非独立测试。',
              'v4': '新增规则按通用句式设计，用虚构景区检查。本批汇总指标用于比较取舍，未按具体漏识名称调整规则。v4复用v3和原词典，当前语料仍属于开发集。',
              'v5': 'v5根据当前语料的漏识类型设计通用规则，同批结果用于开发对照。'}
             .get(args.version, 'v1/v2为修订前冻结基线；评价不改变抽取规则或词典。'))],
    }
    from build_remaining25_gold import write
    write(OUTPUTS / f'evaluation_{args.version}_remaining25.json', payload)
    print(f'{args.version}: {len(scope)} docs, {len(truth)} reference names, {len(pred)} predicted names')
    print('Overall:', payload['overall'])
    for kind, metric in by_type.items():
        print(kind, metric)
    for result in results:
        print(result['scenic_id'], result['overall'])


if __name__ == '__main__':
    main()

"""校验全量产物的位置、样本覆盖、原文版本与人工/助手评价隔离。"""
import hashlib
import sys
from importlib.metadata import version as package_version

from common import BASE, ROOT, OUTPUTS, load_records, read_json, validate_span, write_json
from evaluate import validate_gold


def main():
    records = {r['doc_id']: r for r in load_records()}
    samples = read_json(OUTPUTS / 'samples.json')
    ids = {s['sample_id'] for s in samples}
    if len(ids) != len(samples):
        raise ValueError('代词样本重复')
    gold = read_json(BASE / 'annotations/gold_draft.json')
    validate_gold(gold, records)
    if {i['sample_id'] for i in gold['items']} != ids:
        raise ValueError('默认5篇样本与标注覆盖范围不一致')
    for sample in samples:
        text = records[sample['doc_id']]['clean_text']
        for field in ('pronoun', 'sentence', 'context'):
            validate_span(text, sample[field])
        p, s = sample['pronoun'], sample['sentence']
        if not (s['start'] <= p['start'] < p['end'] <= s['end']):
            raise ValueError('代词与所在句位置错配')
    versions = [v for v in ('v1', 'v2', 'v3', 'v4') if (OUTPUTS / f'predictions_{v}.json').exists()]
    for version in versions:
        predictions = read_json(OUTPUTS / f'predictions_{version}.json')
        if len(predictions) != len(ids) or {p['sample_id'] for p in predictions} != ids:
            raise ValueError('预测遗漏或重复代词样本')
        for prediction in predictions:
            text = records[prediction['doc_id']]['clean_text']
            validate_span(text, prediction['pronoun'])
            if prediction['antecedent']:
                validate_span(text, prediction['antecedent'])
                if prediction['antecedent']['end'] > prediction['pronoun']['start']:
                    raise ValueError('预测先行词位于代词之后')
        links = read_json(OUTPUTS / f'links_{version}.json')
        if len(links) != sum(p['antecedent'] is not None for p in predictions):
            raise ValueError('指代关系数量与消解结果不一致')
        annotated = read_json(OUTPUTS / f'annotated_texts_{version}.json')
        for doc in annotated:
            if doc['original_text'] != records[doc['doc_id']]['clean_text']:
                raise ValueError('展示文本改写了原文')
        evaluation = read_json(OUTPUTS / f'evaluation_{version}.json')
        confirmed = sum(i['review_status'] == 'confirmed' for i in gold['items'])
        if evaluation['human_reviewed_evaluation']['samples'] != confirmed:
            raise ValueError('人工评价混入未确认标注')
        if not confirmed and evaluation['human_reviewed_evaluation']['end_to_end_accuracy'] is not None:
            raise ValueError('没有人工标注却输出人工准确率')
    files = [*sorted((BASE / 'src').glob('*.py')), BASE / 'annotations/gold_draft.json',
             *sorted((ROOT / 'experiments/exp02_entity_recognition/outputs').glob('entities_*_v2.json'))]
    write_json(OUTPUTS / 'run_manifest.json', {
        'python_version': sys.version.split()[0], 'jieba_version': package_version('jieba'),
        'method': 'jieba+rules; no model training, external LLM or experiment3 dependency',
        'versions': versions, 'documents': len({s['doc_id'] for s in samples}),
        'pronoun_occurrences': len(samples), 'human_confirmed_items': confirmed,
        'sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'validation': 'all available versions passed complete output validation',
    })
    print(f'verified: {len(samples)} occurrences, {len(versions)} versions, valid spans and isolated human evaluation')


if __name__ == '__main__':
    main()

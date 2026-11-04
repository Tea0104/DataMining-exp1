"""分别报告助手初标对照与人工复核子集，绝不把未复核初标当成人工金标。"""
import argparse
from collections import Counter
from pathlib import Path

from common import BASE, DATASET, OUTPUTS, load_records, read_json, text_hash, validate_span, write_json


def key(value):
    return (value['start'], value['end'], value['text'])


def validate_gold(gold, records):
    seen = set()
    for doc, expected in gold['source_text_sha256'].items():
        if text_hash(records[doc]['clean_text']) != expected:
            raise ValueError(f'标注文本已变更，必须重新核对偏移: {doc}')
    for item in gold['items']:
        if item['sample_id'] in seen:
            raise ValueError('标注 sample_id 重复')
        seen.add(item['sample_id'])
        if item['doc_id'] not in gold['doc_scope']:
            raise ValueError('标注超出 doc_scope')
        text = records[item['doc_id']]['clean_text']
        validate_span(text, item['pronoun'])
        if item['resolution_status'] not in ('resolved', 'unresolved', 'non_anaphoric'):
            raise ValueError('未知标注状态')
        if bool(item['acceptable_antecedents']) != (item['resolution_status'] == 'resolved'):
            raise ValueError('标注状态与先行词是否存在不一致')
        for ant in item['acceptable_antecedents']:
            validate_span(text, ant)
            if ant['end'] > item['pronoun']['start']:
                raise ValueError('标注先行词不得来自后文')
        if item['review_status'] not in ('pending', 'confirmed'):
            raise ValueError('未知复核状态')
        if item['review_status'] == 'confirmed' and not (item.get('reviewer') or '').strip():
            raise ValueError('人工确认必须填写 reviewer')


def compare(items, predictions):
    rows = []
    for item in items:
        prediction = predictions.get(item['sample_id'])
        if prediction and (prediction['doc_id'] != item['doc_id'] or key(prediction['pronoun']) != key(item['pronoun'])):
            raise ValueError('预测与标注代词错配')
        ant = prediction['antecedent'] if prediction else None
        expected = item['acceptable_antecedents']
        exact = bool(ant and any(key(ant) == key(g) for g in expected))
        text_match = bool(ant and any(ant['text'] == g['text'] for g in expected))
        correct = bool(prediction) and (exact if expected else ant is None)
        rows.append({
            'sample_id': item['sample_id'], 'doc_id': item['doc_id'], 'pronoun': item['pronoun'],
            'gold_status': item['resolution_status'], 'expected': expected, 'predicted': ant,
            'prediction_present': prediction is not None, 'correct': correct,
            'exact_link': exact, 'text_link': text_match,
            'gold_reason': item['reason'], 'prediction_reason': prediction['reason'] if prediction else '缺少预测',
            'review_status': item['review_status'],
            'reference_kind': item.get('reference_kind'),
            'referent_description': item.get('referent_description'),
            'human_interpretation': item.get('human_interpretation'),
        })
    count = len(rows)
    resolved = sum(bool(r['expected']) for r in rows)
    linked = sum(r['predicted'] is not None for r in rows)
    exact = sum(r['exact_link'] for r in rows)
    abstentions = sum(not r['expected'] for r in rows)
    correct_abstentions = sum(not r['expected'] and r['correct'] for r in rows)
    ratio = lambda a, b: round(a / b, 4) if b else None
    precision, recall = ratio(exact, linked), ratio(exact, resolved)
    metrics = {
        'samples': count, 'gold_resolvable': resolved, 'gold_without_antecedent': abstentions,
        'predicted_links': linked, 'exact_correct_links': exact,
        'correct_abstentions': correct_abstentions,
        'missing_predictions': sum(not r['prediction_present'] for r in rows),
        'end_to_end_accuracy': ratio(sum(r['correct'] for r in rows), count),
        'exact_link_precision': precision, 'exact_link_recall': recall,
        'exact_link_f1': round(2 * exact / (linked + resolved), 4) if linked + resolved else None,
        'resolution_coverage': ratio(linked, count),
        'antecedent_text_accuracy_on_resolvable': ratio(sum(r['text_link'] for r in rows), resolved),
        'abstention_accuracy': ratio(correct_abstentions, abstentions),
    }
    return metrics, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--gold', type=Path, default=BASE / 'annotations/gold_draft.json')
    parser.add_argument('--outputs', type=Path, default=OUTPUTS)
    parser.add_argument('--version', choices=('v1', 'v2', 'v3', 'v4'), default='v4')
    args = parser.parse_args()
    records = {r['doc_id']: r for r in load_records(args.input)}
    gold = read_json(args.gold)
    validate_gold(gold, records)
    raw = read_json(args.outputs / f'predictions_{args.version}.json')
    predictions = {p['sample_id']: p for p in raw}
    if len(predictions) != len(raw):
        raise ValueError('预测 sample_id 重复')
    for prediction in raw:
        text = records[prediction['doc_id']]['clean_text']
        validate_span(text, prediction['pronoun'])
        if prediction['antecedent']:
            validate_span(text, prediction['antecedent'])
            if prediction['antecedent']['end'] > prediction['pronoun']['start']:
                raise ValueError('预测使用了后文先行词')
    scope = gold['items']
    reference_metrics, rows = compare(scope, predictions)
    draft = read_json(BASE / gold['draft_snapshot']) if gold.get('draft_snapshot') else gold
    validate_gold(draft, records)
    draft_metrics, _ = compare(draft['items'], predictions)
    confirmed = [i for i in scope if i['review_status'] == 'confirmed']
    human_metrics, _ = compare(confirmed, predictions)
    write_json(args.outputs / f'evaluation_{args.version}.json', {
        'version': args.version, 'gold_file': str(args.gold.relative_to(BASE)) if args.gold.is_relative_to(BASE) else str(args.gold),
        'evaluation_scope': gold['doc_scope'],
        'metric_definition': '逐次代词位置+先行词位置严格匹配；无明确先行词时拒绝链接视为正确；漏预测计错。',
        'annotation_kind': gold.get('annotation_kind'),
        'reference_comparison': reference_metrics,
        'assistant_draft_comparison': draft_metrics,
        'human_reviewed_evaluation': human_metrics,
        'human_review_status': 'available' if confirmed else 'pending; 尚无人为确认的条目，人工指标为null',
        'limitations': ['人工复核与规则开发使用同批语料，不是独立测试或泛化性能。',
                        '来源相同的正文和图注重复保留，案例之间不独立。',
                        '规则仅覆盖部分事件/路线表达；同指实体的不同提及位置可能被严格指标判错。',
                        '图片和现场指示仅保留人工语义说明；空链接正确不代表算法理解了图片。'],
        'by_doc_reference': {d: compare([i for i in scope if i['doc_id'] == d], predictions)[0] for d in gold['doc_scope']},
        'by_target_type_reference': {t: compare([i for i in scope if (i['target_type'] or i['resolution_status']) == t], predictions)[0]
                                 for t in sorted({i['target_type'] or i['resolution_status'] for i in scope})},
        'case_results': rows})
    print(f"{args.version} current-reference comparison: {reference_metrics}; human-confirmed: {len(confirmed)}")


if __name__ == '__main__':
    main()

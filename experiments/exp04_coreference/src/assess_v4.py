"""汇总固定助手逐项判定与五篇人工评价；绝不将25篇称为人工准确率。"""
from collections import Counter
from pathlib import Path
import hashlib

from common import BASE, DATASET, DEFAULT_DOCS, OUTPUTS, load_records, read_json, text_hash, validate_span, write_json
from evaluate import compare, validate_gold


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(counts, total):
    right, uncertain = counts.get('consistent', 0), counts.get('uncertain', 0)
    return {'samples': total, 'counts': {k:counts.get(k, 0) for k in ('consistent', 'inconsistent', 'uncertain')},
            'conservative_agreement': right / total if total else None,
            'optimistic_agreement': (right + uncertain) / total if total else None,
            'human_accuracy': None}


def target(prediction):
    return prediction.get('referent', {}).get('description') or (
        prediction['antecedent']['text'] if prediction['antecedent'] else '未确定前文对象')


def main():
    rest = OUTPUTS / 'remaining25'
    records = {r['doc_id']: r for r in load_records(DATASET)}
    gold_path = BASE / 'annotations/gold_draft.json'
    reference_path = BASE / 'annotations/remaining25_assistant_draft.json'
    judgment_path = BASE / 'annotations/remaining25_v4_assessment.json'
    prediction_path = rest / 'predictions_v4.json'
    human_prediction_path = OUTPUTS / 'predictions_v4.json'
    gold, reference, assessment = map(read_json, (gold_path, reference_path, judgment_path))
    validate_gold(gold, records)
    for field, path in [('reference_sha256', reference_path), ('predictions_sha256', prediction_path),
                        ('human_gold_sha256', gold_path)]:
        if assessment[field] != sha(path):
            raise ValueError(f'{field} 已变化，原助手判定不可继续使用；请重新审阅，不能沿用旧分数。')
    for doc, expected in reference['source_text_sha256'].items():
        if text_hash(records[doc]['clean_text']) != expected:
            raise ValueError(f'助手参考的源文本已变更：{doc}')
    human_raw, remaining_raw = map(read_json, (human_prediction_path, prediction_path))
    expected_ids = {r['sample_id'] for r in reference['items']}
    samples = read_json(rest / 'samples.json')
    if expected_ids != {r['sample_id'] for r in samples}:
        raise ValueError('25篇检测样本与固定参考不一致')
    for raw in (human_raw, remaining_raw):
        if len({p['sample_id'] for p in raw}) != len(raw):
            raise ValueError('重复预测')
        for p in raw:
            text = records[p['doc_id']]['clean_text']
            validate_span(text, p['pronoun'])
            if p['antecedent']:
                validate_span(text, p['antecedent'])
                if p['antecedent']['end'] > p['pronoun']['start']:
                    raise ValueError('预测取用了后文先行词')
    if len(remaining_raw) != len(expected_ids) or {p['sample_id'] for p in remaining_raw} != expected_ids:
        raise ValueError('25篇预测缺失、多余或重复')
    if len(assessment['items']) != len(expected_ids) or {r['sample_id'] for r in assessment['items']} != expected_ids:
        raise ValueError('助手判定覆盖不完整或重复')
    predictions = {p['sample_id']: p for p in remaining_raw}
    references = {r['sample_id']: r for r in reference['items']}
    rows = []
    for row in assessment['items']:
        if row['verdict'] not in ('consistent', 'inconsistent', 'uncertain') or not row['reason']:
            raise ValueError('未知或缺少理由的助手判定')
        p, r = predictions[row['sample_id']], references[row['sample_id']]
        if p['pronoun'] != r['pronoun'] or p['doc_id'] != r['doc_id']:
            raise ValueError('助手参考与预测错配')
        rows.append({**row, 'doc_id': r['doc_id'], 'number': r['number'], 'pronoun': r['pronoun'],
                     'reference': r['referent_description'], 'prediction': target(p),
                     'algorithm_reason': p['reason']})
    if any(r['review_status'] != 'pending' or r.get('reviewer') for r in reference['items']):
        raise ValueError('25篇人工复核状态已变化，需重新设计评价来源分组')
    human_items = [r for r in gold['items'] if r['review_status'] == 'confirmed']
    human_metrics, human_rows = compare(human_items, {p['sample_id']: p for p in human_raw})
    human_correct = sum(r['correct'] for r in human_rows)
    counts = Counter(r['verdict'] for r in rows)
    remaining = summarize(counts, len(rows))
    mixed_counts = counts.copy()
    mixed_counts['consistent'] += human_correct
    mixed_counts['inconsistent'] += len(human_rows) - human_correct
    mixed = summarize(mixed_counts, len(human_rows) + len(rows))
    mixed['metric_kind'] = 'mixed_reference_and_criteria_weighted_summary_not_full_human_accuracy'
    by_doc = {}
    for doc in reference['scope_docs']:
        subset = [r for r in rows if r['doc_id'] == doc]
        by_doc[doc] = summarize(Counter(r['verdict'] for r in subset), len(subset))
    summary = {
        'version': 'v4', 'documents': 30, 'detected_candidates': len(human_rows) + len(rows),
        'human_reviewed_5': {'documents': 5, 'correct': human_correct, **human_metrics},
        'assistant_reference_25': {'documents': 25, **remaining},
        'overall_mixed_reference': mixed, 'by_doc_remaining25': by_doc,
        'hashes': {str(p.relative_to(BASE)).replace('\\', '/'): sha(p)
                   for p in (gold_path, reference_path, judgment_path, prediction_path, human_prediction_path, DATASET)
                   if p.is_relative_to(BASE)},
        'limitations': [
            '仅五篇有用户人工金标；25篇是固定助手初标与助手语义判定，不是真实人工准确率。',
            '五篇采用严格先行词位置匹配；25篇允许同指异名，按语义完整性判断。总体只是两种口径按样本数加权的参考汇总。',
            '30篇均已参与规则开发和检查，全部属于开发数据；没有独立真实测试集，不能据此断言新文章上的泛化性能。',
            '分母是204处检测候选，不是文章数；6篇无候选，逐篇指标留空。未评价漏检，固定表达误检也保留在分母。',
            '待定项保留在分母，保守值只计明确一致；上界假设待定全部一致，不是统计置信区间。',
            '场景、图片、篇章指示可以用说明表达；不读取图片，不将说明伪造成正文先行词。'],
        'case_results_remaining25': rows}
    write_json(OUTPUTS / 'v4_results.json', summary)
    write_json(rest / 'assistant_agreement_v4.json', {'assessment_kind': assessment['assessment_kind'],
               **remaining, 'human_reviewed_items': 0, 'by_doc': by_doc, 'cases': rows})
    pct = lambda n: f'{n:.2%}' if n is not None else '不适用'
    old = read_json(rest / 'assistant_agreement.json')
    old_human = read_json(OUTPUTS / 'evaluation_v3.json')['human_reviewed_evaluation']
    old_right = round(old_human['end_to_end_accuracy'] * old_human['samples'])
    old_mixed = (old_right + old['counts']['consistent']) / mixed['samples']
    lines = ['# v4实验结果（开发数据）', '',
             '| 范围 | v3 | v4 | v4明确一致/候选数 |', '|---|---:|---:|---:|',
             f"| 五篇人工复核：严格准确率 | {pct(old_human['end_to_end_accuracy'])} | {pct(human_metrics['end_to_end_accuracy'])} | {human_correct}/{len(human_rows)} |",
             f"| 剩余25篇：助手语义参考一致率，保守值 | {pct(old['conservative_agreement'])} | {pct(remaining['conservative_agreement'])} | {counts['consistent']}/{len(rows)} |",
             f"| 30篇：混合口径加权参考值，保守值 | {pct(old_mixed)} | {pct(mixed['conservative_agreement'])} | {mixed_counts['consistent']}/{mixed['samples']} |", '',
             f"25篇：明确一致{counts['consistent']}处、不一致{counts['inconsistent']}处、待定{counts['uncertain']}处。待定全计正确时为{pct(remaining['optimistic_agreement'])}；总体上界为{pct(mixed['optimistic_agreement'])}。", '',
             '准确率按代词出现次数计算，不对每篇百分比直接取平均。五篇严格匹配与25篇语义匹配采用不同口径，总体仅便于查看开发效果，不能作为全量人工准确率。', '',
             '## 评价范围与限制', '', *['- ' + s for s in summary['limitations']], '',
             '## 剩余25篇逐篇结果', '',
             '| 文章编号（点击查看完整预测） | 候选数 | 明确一致 | 不一致 | 待定 | 保守一致率 |',
             '|---|---:|---:|---:|---:|---:|']
    articles = rest / 'v4_articles'
    articles.mkdir(exist_ok=True)
    for doc, m in by_doc.items():
        c = m['counts']
        lines.append(f"| [{doc}](remaining25/v4_articles/{doc}.md) | {m['samples']} | {c.get('consistent',0)} | {c.get('inconsistent',0)} | {c.get('uncertain',0)} | {pct(m['conservative_agreement'])} |")
        items = [r for r in rows if r['doc_id'] == doc]
        marked = records[doc]['clean_text']
        labels = {'consistent': '与助手参考一致', 'inconsistent': '与助手参考不一致', 'uncertain': '待定'}
        for row in sorted(items, key=lambda r:r['pronoun']['start'], reverse=True):
            p = row['pronoun']
            marker = f"**{p['text']}**【第{row['number']}处；v4预测：{row['prediction'].replace(chr(10),' ')}；{labels[row['verdict']]}】"
            marked = marked[:p['start']] + marker + marked[p['end']:]
        page = [f"# {records[doc]['title']}", '', '程序预测及助手参考比较；未经用户人工复核。', '',
                f"[原网页]({records[doc].get('source_url','')})", '', marked, '', '## 每处对照与理由', '']
        for row in items:
            page += [f"- 第{row['number']}处：{labels[row['verdict']]}。固定参考：{row['reference']}。判定：{row['reason']}。算法理由：{row['algorithm_reason']}。"]
        if not items:
            page += ['未检出当前词表内候选；没有可计算的一致率，不能记作100%。']
        (articles / f'{doc}.md').write_text('\n'.join(page) + '\n', encoding='utf-8')
    lines += ['', '## 尚未解决的明确错误', '']
    if not counts['inconsistent']:
        lines += ['本次助手语义裁定没有明确不一致项；待定项仍未确认，不能据此称全部正确。', '']
    for row in rows:
        if row['verdict'] == 'inconsistent':
            lines += [f"- 第{row['number']}处（{row['doc_id']}）：预测“{row['prediction']}”；参考“{row['reference']}”；{row['reason']}。"]
    lines += ['', '## 保留待定的案例（未计入保守正确数）', '']
    for row in rows:
        if row['verdict'] == 'uncertain':
            lines += [f"- 第{row['number']}处（{row['doc_id']}）：{row['reason']}"]
    (OUTPUTS / 'v4_results.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print({'human5': human_metrics['end_to_end_accuracy'], 'assistant25': remaining, 'mixed30': mixed})


if __name__ == '__main__':
    main()

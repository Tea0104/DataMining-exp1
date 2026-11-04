"""用固定v3处理原五篇以外的文本，输出预测统计和逐篇原文标注，不计算准确率。"""
import argparse
import hashlib
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import BASE, DATASET, DEFAULT_DOCS, OUTPUTS, ROOT, load_records, read_json, validate_span, write_json
from resolve import render_annotations


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--exclude-docs', nargs='+', default=list(DEFAULT_DOCS))
    parser.add_argument('--outputs', type=Path, default=OUTPUTS / 'remaining25')
    args = parser.parse_args()
    if args.outputs.resolve() == OUTPUTS.resolve():
        parser.error('请使用单独输出目录，保留已复核五篇的结果')
    records = load_records(args.input)
    selected = [r for r in records if r['doc_id'] not in args.exclude_docs]
    if not selected:
        parser.error('排除后没有剩余文章')
    if set(args.exclude_docs) - {r['doc_id'] for r in records}:
        parser.error('排除列表包含未知文档')
    protected = [BASE / 'annotations/gold_draft.json', *OUTPUTS.glob('evaluation_v*.json'),
                 *OUTPUTS.glob('predictions_v*.json'), OUTPUTS / 'gold_review.md']
    protected_hashes = {p: sha(p) for p in protected if p.exists()}
    src = BASE / 'src'
    model_files = [src / p for p in ('detect.py', 'resolve.py', 'context_rules.py', 'common.py')]
    model_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in model_files}
    args.outputs.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(src / 'detect.py'), '--input', str(args.input),
                    '--docs', *[r['doc_id'] for r in selected], '--outputs', str(args.outputs)], check=True)
    subprocess.run([sys.executable, str(src / 'resolve.py'), '--version', 'v3', '--input', str(args.input),
                    '--samples', str(args.outputs / 'samples.json'), '--outputs', str(args.outputs)], check=True)
    samples = read_json(args.outputs / 'samples.json')
    predictions = read_json(args.outputs / 'predictions_v3.json')
    if len(predictions) != len(samples) or {p['sample_id'] for p in predictions} != {s['sample_id'] for s in samples}:
        raise ValueError('预测与检测结果遗漏、重复或错配')
    if len({p['sample_id'] for p in predictions}) != len(predictions):
        raise ValueError('存在重复预测')
    by_doc = defaultdict(list)
    selected_by_id = {r['doc_id']: r for r in selected}
    for prediction in predictions:
        doc = prediction['doc_id']
        if doc not in selected_by_id:
            raise ValueError('预测混入已排除文章')
        text = selected_by_id[doc]['clean_text']
        validate_span(text, prediction['pronoun'])
        if prediction['antecedent']:
            validate_span(text, prediction['antecedent'])
            if prediction['antecedent']['end'] > prediction['pronoun']['start']:
                raise ValueError('先行词位置不合法')
        by_doc[doc].append(prediction)
    doc_rows = []
    for record in selected:
        items = by_doc[record['doc_id']]
        linked = sum(p['antecedent'] is not None for p in items)
        doc_rows.append({
            'doc_id': record['doc_id'], 'title': record['title'],
            'scenic_id': record['scenic_id'], 'scenic_name': record['scenic_name'],
            'text_type': record['text_type'], 'pronouns': len(items),
            'predicted_links': linked, 'unresolved': len(items) - linked,
            'source_url': record.get('source_url'), 'human_reviewed': False})
    linked = sum(row['predicted_links'] for row in doc_rows)
    summary = {
        'version': 'v3', 'evaluation_status': 'unreviewed_inference_only',
        'excluded_docs': args.exclude_docs, 'documents': len(selected),
        'document_types': dict(Counter(r['text_type'] for r in selected)),
        'detected_pronouns': len(samples), 'predicted_links': linked,
        'unresolved': len(samples) - linked,
        'automatic_link_rate': round(linked / len(samples), 4) if samples else None,
        'accuracy': None, 'precision': None, 'recall': None,
        'note': '自动链接率不是准确率；未人工标注，不能评价检测漏识或消解错误率。',
        'documents_with_pronouns': sum(r['pronouns'] > 0 for r in doc_rows),
        'documents_without_detected_pronouns': [r['doc_id'] for r in doc_rows if not r['pronouns']],
        'by_scenic': {s: {
            'documents': sum(r['scenic_id'] == s for r in doc_rows),
            'pronouns': sum(r['pronouns'] for r in doc_rows if r['scenic_id'] == s),
            'predicted_links': sum(r['predicted_links'] for r in doc_rows if r['scenic_id'] == s),
            'unresolved': sum(r['unresolved'] for r in doc_rows if r['scenic_id'] == s)}
            for s in dict.fromkeys(r['scenic_id'] for r in doc_rows)},
        'by_doc': doc_rows, 'model_source_sha256': model_hashes,
        'input_sha256': sha(args.input), 'human_reviewed_items': 0,
        'verification': '全部检测样本均有预测；代词与先行词位置合法；已复核五篇及金标未改动。',
    }
    write_json(args.outputs / 'summary.json', summary)
    # 即使某篇未检出代词，也保留该篇文本和零计数，不能悄悄跳过。
    write_json(args.outputs / 'annotated_texts_v3.json', [
        {'doc_id': r['doc_id'], 'source_url': r.get('source_url'), 'original_text': r['clean_text'],
         'annotated_text': render_annotations(r['clean_text'], by_doc[r['doc_id']]),
         'offsets_refer_to': 'original_text', 'human_reviewed': False}
        for r in selected])
    articles_dir = args.outputs / 'articles'
    articles_dir.mkdir(exist_ok=True)
    all_articles = ['# 剩余文章的程序预测原文标注', '',
                    '每一处都是v3程序预测，尚未人工核验。加粗的是检测到的代词；“未能确定”也可能是算法漏解，不等于原文没有指代对象。', '']
    for article_index, record in enumerate(selected, 1):
        items = sorted(by_doc[record['doc_id']], key=lambda p: p['pronoun']['start'])
        annotated = record['clean_text']
        for index in range(len(items) - 1, -1, -1):
            prediction = items[index]
            p, ant = prediction['pronoun'], prediction['antecedent']
            target = '程序推测指“' + ' '.join(ant['text'].split()) + '”' if ant else '程序未能确定前文对象'
            marker = f"**{p['text']}**【第{index + 1}处：{target}】"
            annotated = annotated[:p['start']] + marker + annotated[p['end']:]
        page = [f"# {record['title']}", '',
                f"文章编号：{record['doc_id']}；本篇检测到{len(items)}处代词。以下均为未经人工核验的程序预测。", '',
                f"[原网页]({record.get('source_url', '')})", '', annotated, '', '## 每处预测的理由', '']
        page += [f"- 第{i}处“{p['pronoun']['text']}”：{p['reason']}。" for i, p in enumerate(items, 1)]
        if not items:
            page += ['本篇未检出当前词表范围内的代词，不代表整篇已被人工确认无指代。']
        (articles_dir / f"{record['doc_id']}.md").write_text('\n'.join(page).rstrip() + '\n', encoding='utf-8', newline='\n')
        all_articles += [f"## 文章{article_index} {record['title']}", '',
                         f"编号：{record['doc_id']}；检测{len(items)}处。", '', annotated, '', '---', '']
    (args.outputs / 'annotated_articles.md').write_text('\n'.join(all_articles).rstrip() + '\n', encoding='utf-8', newline='\n')
    lines = ['# 剩余25篇实验四预测结果', '',
             f"使用原v3算法处理{len(selected)}篇，排除此前已复核的5篇。检测到{len(samples)}处代词，程序建立{linked}条前文指代链接，{len(samples) - linked}处未确定。", '',
             '这批没有人工标注，准确率、精确率和召回率均未计算；链接数量不是正确数量。算法与之前开发集评价时保持一致。', '',
             f"[查看全部25篇原文标注]({(args.outputs / 'annotated_articles.md').resolve().as_posix()})", '',
             '| 文章（点击查看原文标注） | 类型 | 代词 | 已链接 | 未确定 |',
             '|---|---|---:|---:|---:|']
    for row in doc_rows:
        title = row['title'].replace('|', '｜').replace('\\', '／')
        target = (articles_dir / f"{row['doc_id']}.md").resolve().as_posix()
        lines.append(f"| [{title}]({target}) | {'官方路线' if row['text_type'] == 'official_route' else '游客游记'} | {row['pronouns']} | {row['predicted_links']} | {row['unresolved']} |")
    (args.outputs / 'results.md').write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8', newline='\n')
    for path, expected in protected_hashes.items():
        if sha(path) != expected:
            raise ValueError(f'已复核数据或原结果被改变: {path}')
    if any(sha(path) != model_hashes[path.relative_to(ROOT).as_posix()] for path in model_files):
        raise ValueError('运行期间模型源码发生变化')
    print(f"remaining inference: {len(selected)} documents; {len(samples)} pronouns; {linked} linked; {len(samples) - linked} unresolved")
    print('Validated all spans and scope; reviewed five-document outputs unchanged; no accuracy computed.')


if __name__ == '__main__':
    main()

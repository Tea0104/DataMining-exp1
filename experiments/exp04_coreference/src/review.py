"""输出逐条复核表、正确及错误案例；不修改标注或复核状态。"""
import argparse
import hashlib
from pathlib import Path

from common import BASE, DATASET, OUTPUTS, load_records, read_json


def percent(value):
    return f'{value:.2%}' if value is not None else '不适用'


def describe(ant):
    return f"{ant['text'].replace(chr(10), ' ⏎ ')} [{ant['start']},{ant['end']})" if ant else '无正文先行词链接'


def table_cell(value):
    return str(value).replace('|', '｜').replace('\n', ' ⏎ ')


def render_analysis(gold, evaluations, summary=None, old_assessment=None):
    """从当前评价生成分析，不把历史版本或助手参考写成人工准确率。"""
    versions = list(evaluations)
    latest = versions[-1]
    results = {v:{r['sample_id']:r for r in e['case_results']} for v,e in evaluations.items()}
    confirmed = sum(i['review_status'] == 'confirmed' for i in gold['items'])
    analysis = [f'# 共指消解误差分析 {latest}', '',
                f'当前版本为{latest}。五篇中{confirmed}处已由用户人工复核；旧版本仅作为同一标注上的开发对照。本文是结果检查说明，不是正式实验报告。', '',
                '## 五篇人工复核的版本对照', '',
                '| 版本 | 人工样本数 | 严格准确率 | 链接精确率 | 链接召回率 | 文字链接覆盖率 |',
                '|---|---:|---:|---:|---:|---:|']
    for v,e in evaluations.items():
        m = e['human_reviewed_evaluation']
        analysis.append(f"| {v} | {m['samples']} | {percent(m['end_to_end_accuracy'])} | {percent(m['exact_link_precision'])} | {percent(m['exact_link_recall'])} | {percent(m['resolution_coverage'])} |")
    analysis += ['', '严格准确要求代词位置和先行词位置匹配；人工标为无正文前置对象时，保留空链接才算正确。空链接正确不等于算法理解了图片或现场。上述数据已经用于规则开发，不是独立测试。', '',
                 f'## {latest}人工样本中的不匹配', '']
    failures = [r for r in results[latest].values() if not r['correct']]
    if not failures:
        analysis += [f'当前{confirmed}处人工复核案例没有严格不匹配；不能由此断言其他文章没有错误。']
    for r in failures:
        analysis += [f"- `{r['sample_id']}`：预测{describe(r['predicted'])}；人工参考{' / '.join(describe(a) for a in r['expected']) or '无正文前置对象'}。{r['gold_reason']}"]
    if 'v2' in results and latest != 'v2':
        repaired = [r for sid,r in results[latest].items() if r['correct'] and not results['v2'][sid]['correct']]
        regressed = [r for sid,r in results[latest].items() if not r['correct'] and results['v2'][sid]['correct']]
        analysis += ['', f'## 人工标注支持的历史错误与{latest}修复', '',
                     f"相对v2修复{len(repaired)}处严格不匹配，新增不匹配{len(regressed)}处。以下对比使用同一份用户标注，未更改标注以提高结果。", '',
                     '| 样本 | v2预测 | 人工参考 | 当前预测 | 原因与处理 |', '|---|---|---|---|---|']
        by_id = {i['sample_id']:i for i in gold['items']}
        seen = set()
        for r in repaired:
            kind = by_id[r['sample_id']].get('target_type') or r['gold_status']
            if kind in seen:
                continue
            seen.add(kind)
            old = results['v2'][r['sample_id']]
            expected = ' / '.join(describe(a) for a in r['expected']) or '无正文前置对象'
            cells = [r['sample_id'], describe(old['predicted']), expected, describe(r['predicted']), r['prediction_reason']]
            analysis.append('| ' + ' | '.join(table_cell(c) for c in cells) + ' |')
            if len(seen) == 4:
                break
    if summary:
        human, rest, mixed = summary['human_reviewed_5'], summary['assistant_reference_25'], summary['overall_mixed_reference']
        counts = rest['counts']
        analysis += ['', '## 当前v4三组结果与评价口径', '',
                     '| 范围 | 结果 | 正确或明确一致数 / 候选数 | 参考来源 |', '|---|---:|---:|---|',
                     f"| 五篇严格准确率 | {percent(human['end_to_end_accuracy'])} | {human['correct']}/{human['samples']} | 用户人工标注 |",
                     f"| 25篇保守语义一致率 | {percent(rest['conservative_agreement'])} | {counts['consistent']}/{rest['samples']} | 固定助手初标及助手裁定 |",
                     f"| 30篇混合口径参考值 | {percent(mixed['conservative_agreement'])} | {mixed['counts']['consistent']}/{mixed['samples']} | 上述两种口径按候选数加权 |", '',
                     f"25篇共{counts['consistent']}处明确一致、{counts['inconsistent']}处明确不一致、{counts['uncertain']}处待定。待定留在分母，未计为正确。混合参考值不是全量人工准确率，不能与前五篇的严格指标作为同一口径解释。", '',
                     '详细逐篇原文标注见[v4结果汇总](v4_results.md)。六篇没有检测候选，逐篇指标记为不适用；没有把空篇记作100%。', '',
                     '## v4待定案例及原因', '',
                     '这些案例未经用户复核。下表保留原裁定，不在补写分析时改成正确或错误。', '',
                     '| 编号 | 文章 | 代词 | v4预测 | 固定助手参考 | 待定原因 |', '|---:|---|---|---|---|---|']
        for r in summary['case_results_remaining25']:
            if r['verdict'] == 'uncertain':
                cells = [r['number'], r['doc_id'], r['pronoun']['text'], r['prediction'], r['reference'], r['reason']]
                analysis.append('| ' + ' | '.join(table_cell(c) for c in cells) + ' |')
        analysis += ['', '待定主要来自整体与局部范围不同、事件跨度过宽或包含残缺分句、未明说的管理方，以及原文地名疑有笔误。可进一步区分地点与局部区域、事件与背景，并核对歧义来源；这些是后续改进方向，本次未改算法或裁定。']
        if old_assessment:
            old = {r['sample_id']:r for r in old_assessment['cases']}
            changed = [r for r in summary['case_results_remaining25']
                       if r['verdict'] == 'consistent' and old.get(r['sample_id'],{}).get('verdict') == 'inconsistent']
            analysis += ['', '## 其余文章的历史误指与v4改善示例', '',
                         '以下为助手语义参考下的改善，不是新增人工验证。v3对照来自保留的原预测；v4结果和参考均从当前结构化文件读取。', '',
                         '| 类型 | 样本 | v3预测 | v4预测 | 固定助手参考 |', '|---|---|---|---|---|']
            for label, cue in [('完整路线', '线路'), ('小节场所', '小节'), ('动物', '动物')]:
                r = next((r for r in changed if cue in r['algorithm_reason']), None)
                if r:
                    previous = old[r['sample_id']]['prediction']
                    cells = [label, r['sample_id'], previous['text'] if previous else '无链接', r['prediction'], r['reference']]
                    analysis.append('| ' + ' | '.join(table_cell(c) for c in cells) + ' |')
            analysis += ['', f"v3的25篇助手参考保守一致率为{percent(old_assessment['conservative_agreement'])}，当前v4为{percent(rest['conservative_agreement'])}。两者均属于已查看语料的开发对照，不是新文章的泛化准确率。"]
    elif latest == 'v4':
        analysis += ['', '## 25篇与总体结果尚未汇总', '', '请先运行src/run_v4.py；当前只有五篇人工指标，不推算其他文章的准确率。']
    analysis += ['', '## 方法与局限', '',
                 'v1为最近名词基线，v2增加类型和距离约束，v3补充路线、事件及地点集合，v4进一步判断指代意图，利用完整名词、小节主题、行程和时间语境。推理不读取人工标注或助手裁定，不按文档编号分支；本次材料整理不改消解规则。', '',
                 '所有30篇均已用于开发和检查，没有独立真实测试集。现有词表只覆盖部分第三人称及指示用法，未对全文漏检系统评估；47项合成及回归测试用于检查程序行为，不能作为真实文章准确率。', '',
                 '图片和现场对象只能保存文字说明或拒绝不可靠的正文链接；程序没有读取图片。resolution_status描述文字链接状态，referent可以补充非文本对象说明；覆盖率不能代替准确率。', '',
                 '本次无需实验三，未训练模型，也未在推理时调用外部LLM。正式实验报告仍未编写。']
    return '\n'.join(analysis).rstrip() + '\n'


def render_full_review(gold, records):
    """供人工阅读的五篇原文；只插入标记，不改写原文章或标注状态。"""
    confirmed = sum(i['review_status'] == 'confirmed' for i in gold['items'])
    review_intro = (f'已有{confirmed}处经用户人工复核。人工修改已合入下文，复核批注原件另存于 archive/human_review_20261102/。'
                    if confirmed else '这些说明是助手初标，可能有错，目前均待你复核。')
    lines = ['# 实验四 五篇文章的原文标注', '',
             '下面是五篇文章在实验一中保留的完整文本。加粗的是需要你检查的代词，紧跟的方括号说明它可能指什么。', '',
             review_intro + '你可以继续按编号指出需要更正之处，无需修改代码或JSON。', '',
             '例如：到了万仙楼，**这里**（指万仙楼）是泰山检票口。', '',
             '这里保留的是所选景区范围的清洗文本，不一定是原网站跨城游记的全部内容。', '']
    numbering = {item['sample_id']: i for i, item in enumerate(gold['items'], 1)}
    for article_index, doc in enumerate(gold['doc_scope'], 1):
        record = records[doc]
        items = [i for i in gold['items'] if i['doc_id'] == doc]
        annotated = record['clean_text']
        for item in sorted(items, key=lambda i: i['pronoun']['start'], reverse=True):
            p = item['pronoun']
            index = numbering[item['sample_id']]
            if item['acceptable_antecedents']:
                targets = [' '.join(a['text'].split()) for a in item['acceptable_antecedents']]
                judgment = '指“' + '”或“'.join(targets) + '”'
            elif '后指' in item['reason']:
                judgment = '指后面的引语，不是回指前文'
            elif '照片' in item['reason'] or '图片' in item['reason'] or '图像' in item['reason']:
                judgment = '文字中没有明确对象，可能需要看图片'
            elif item['resolution_status'] == 'unresolved':
                judgment = '暂不能确定指什么'
            else:
                judgment = '没有明确的前文对象'
            judgment = item.get('review_display', judgment)
            status = '；已确认' if item['review_status'] == 'confirmed' else ''
            marked = f"**{p['text']}**【第{index}处：{judgment}{status}】"
            annotated = annotated[:p['start']] + marked + annotated[p['end']:]
        lines += [f"## 文章{article_index} {record['title']}", '',
                  f"景区：{record.get('scenic_name', record['scenic_id'])}。本篇有{len(items)}处标注。", '',
                  f"[查看原网页]({record.get('source_url', '')})", '', annotated, '', '---', '']
    lines += ['## 没有正文前置对象的标注说明', '', '这里包括后指引语、图片对象、现场指示和指示限定用法；不等于这些表达毫无指代意义。', '']
    for item in gold['items']:
        if not item['acceptable_antecedents']:
            lines.append(f"- 第{numbering[item['sample_id']]}处“{item['pronoun']['text']}”：{item['reason']}")
    return '\n'.join(lines).rstrip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DATASET)
    parser.add_argument('--gold', type=Path, default=BASE / 'annotations/gold_draft.json')
    parser.add_argument('--outputs', type=Path, default=OUTPUTS)
    args = parser.parse_args()
    gold = read_json(args.gold)
    records = {r['doc_id']: r for r in load_records(args.input)}
    versions = [v for v in ('v1', 'v2', 'v3', 'v4') if (args.outputs / f'evaluation_{v}.json').exists()]
    evaluations = {v: read_json(args.outputs / f'evaluation_{v}.json') for v in versions}
    results = {v: {r['sample_id']: r for r in e['case_results']} for v, e in evaluations.items()}
    confirmed = sum(i['review_status'] == 'confirmed' for i in gold['items'])
    summary = None
    summary_path = args.outputs / 'v4_results.json'
    if 'v4' in versions and summary_path.exists():
        summary = read_json(summary_path)
        if summary['version'] != 'v4':
            raise ValueError('v4汇总版本不匹配')
        for relative, expected in summary['hashes'].items():
            if hashlib.sha256((BASE / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f'v4汇总已过期：{relative}；请先运行src/run_v4.py更新评价。')
        current = evaluations['v4']['human_reviewed_evaluation']
        if any(summary['human_reviewed_5'][k] != v for k,v in current.items()):
            raise ValueError('v4汇总与五篇人工评价不一致，请重新汇总')
    old_path = args.outputs / 'remaining25/assistant_agreement.json'
    old_assessment = read_json(old_path) if summary and old_path.exists() else None
    lines = ['# 实验四标注复核对照表', '',
             f'当前共{len(gold["items"])}项标注，其中{confirmed}项已人工确认。请先阅读原文与标注理由，再展开算法结果。', '',
             '确认后在 annotations/gold_draft.json 对应条目填写 review_status="confirmed" 及 reviewer；需要修正时先修改先行词和理由，再确认。不要把所有条目批量当作已复核。', '',
             '先行词为原文 Python 字符位置，左闭右开。同名不同位置的代词单独标注；无明确先行词保留空值。', '']
    for index, item in enumerate(gold['items'], 1):
        p = item['pronoun'];text = records[item['doc_id']]['clean_text']
        context = text[max(0, p['start'] - 240):min(len(text), p['end'] + 100)]
        lines += [f"## {index} {item['sample_id']} {p['text']}", '',
                  f"来源：[原文章]({records[item['doc_id']].get('source_url', '')})；复核状态：{item['review_status']}。", '',
                  '```text', context, '```', '',
                  f"标注：{item['resolution_status']}；先行词：{' / '.join(describe(a) for a in item['acceptable_antecedents']) or '无正文前置对象'}。", '',
                  f"理由：{item['reason']}", '', '<details><summary>展开算法结果</summary>', '']
        for v in versions:
            r = results[v][item['sample_id']]
            lines += [f"{v}：{describe(r['predicted'])}；与当前标注严格匹配：{'是' if r['correct'] else '否'}。理由：{r['prediction_reason']}", '']
        lines += ['</details>', '']
    (args.outputs / 'gold_review_details.md').write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8', newline='\n')
    (args.outputs / 'gold_review.md').write_text(render_full_review(gold, records), encoding='utf-8', newline='\n')
    (args.outputs / 'error_analysis.md').write_text(render_analysis(gold, evaluations, summary, old_assessment),
                                                 encoding='utf-8', newline='\n')
    print('Wrote full-article gold_review.md, technical details and error analysis; review states unchanged')


if __name__ == '__main__':
    main()

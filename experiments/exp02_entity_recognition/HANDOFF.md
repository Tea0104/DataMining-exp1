# 实验二侧栏聊天交接记录 2026年11月2日

这份记录用于主聊天或后续接手时恢复上下文。本次侧栏工作仅涉及实验二，不说明实验四当前完成程度。实验四及其他模块以对应目录和主聊天记录为准。

## 现在做到哪里

当前最新实现为 **v3**，已运行全部30篇，输出1667条实体。v2保留作为基线，没有在v2文件上覆盖生成v3结果。正式实验报告正文仍未编写。

用户关注的不只是原5篇样本的高分，还包括剩余文章的召回率和换数据后的适用性。最后已明确：本轮改进有可复用规则，但指标是在现有语料上调试后得到的，尚未证明新数据能有相近效果。

## 金标和评价范围

| 范围 | 名称级参考条目 | 标注与复核状态 | 文件入口 |
|---|---:|---|---|
| 原5篇 | 127 | 用户确认已复核原gold_review记录，随后授权合入13项审计修订；原件已归档 | outputs/gold_TAISHAN.json等及outputs/gold_review.md |
| 其余25篇 | 882 | 由助手逐篇阅读原文标注；用户明确本轮不再人工复核，不得写成人工金标准 | annotations/remaining25_labels.json及outputs/gold_remaining25.json |

两批合计覆盖30篇，但评价结果分别保存，不要把原5篇的100%描述成全部30篇准确率。25篇的原始名称清单有883项，其中同篇“10分钟”与“10 分钟”按现有忽略空白的评价口径合并，最终为882项。

评价键为`doc_id + entity_type + 去空白的原文名称`。同名多次出现只计一次，严格区分全称、简称、别名与短片段。每项参考标注有原文位置证据，但不等于每次出现都有人逐条核验。

## 固定25篇上的最终结果

| 指标 | v2基线 | v3当前 |
|---|---:|---:|
| TP | 550 | 739 |
| FP | 25 | 23 |
| FN | 332 | 143 |
| 精确率 | 95.65% | 96.98% |
| 召回率 | 62.36% | 83.79% |
| F1 | 75.50% | 89.90% |

v3分类型召回率：POI 74.12%，交通100%，时间95.75%。新恢复192项原先漏识，同时损失3项原先命中，净增加189项命中；没有只计成功案例。

原5篇另算：v3 TP126、FP3、FN1，精确率97.67%、召回率99.21%、F1 98.44%。它比v2原5篇的100%略有退化，已保留该结果。详见`outputs/evaluation_v3_sample5.json`。

## 本次具体改动

1. 新增25篇原文名称清单和带字符位置证据的参考标注，分景区和合并版本均保存；先保存标注再读取本轮预测对照，未从预测列表直接复制金标。
2. 新增`src/build_remaining25_gold.py`，只读取人工整理形式的助手标注清单和原文，不读取预测或识别词典；校验原文位置、篇数和哈希。
3. 新增`src/evaluate_remaining25.py`，只评价这25篇，输出独立文件，不覆盖原5篇评价；已支持v1、v2、v3。
4. 新增`src/recognize_v3.py`，复用v2的217词词典，增加字符串匹配、设施边界扩展、明确路线节点、别名与题刻候选、词性和通名过滤。
5. 补充可复用交通表达与地铁/轻轨线路规则；修复“换乘索道”被当成具名线路的问题。
6. 补充日期、季节、星期、相对日、模糊中文时长、秒数及标签冒号后的时刻范围；排除历史日期、诗句“九天云气”、非时间用法“一时爽”等。
7. 新增`tests/test_v3.py`的13项规则回归；连同原11项，共24项通过。对全部30篇1667条结果完成位置、重复、重叠、分类计数和CSV词频校验，三张v3词频图已查看。

**本次v3没有修改原识别器`src/recognize_entities.py`或`src/config/lexicon.json`，也没有把882项参考标注整表加入词典。** v2输出、参考标注、原词典等27个文件已做前后哈希校验，记录在`outputs/v3_improvement.json`。

## 文件入口

- 当前实现：[recognize_v3.py](src/recognize_v3.py)。独立入口，不是原脚本加`--version v3`。
- 25篇评价：[evaluate_remaining25.py](src/evaluate_remaining25.py)。
- 结果说明：[v3_improvement.md](outputs/v3_improvement.md)。
- 前后对比与保留文件哈希：[v3_improvement.json](outputs/v3_improvement.json)。
- 逐篇结果与剩余漏识：[evaluation_v3_remaining25.json](outputs/evaluation_v3_remaining25.json)。
- 新增参考标注：[gold_remaining25.json](outputs/gold_remaining25.json)。
- 标注清单及导出校验：[remaining25_labels.json](annotations/remaining25_labels.json)、[gold_remaining25_manifest.json](outputs/gold_remaining25_manifest.json)。
- 当前30篇统计：[stats_all_v3.json](outputs/stats_all_v3.json)。实体、统计、CSV及图片都使用`_v3`后缀。
- 本次记录的文件快照：[handoff_20261102_snapshot.json](outputs/handoff_20261102_snapshot.json)。包含当前实现和主要结果的SHA256，便于后续识别文件是否已变化。

注意：旧`outputs/evaluation.json`和`evaluation_v2.json`对应原5篇；默认运行旧识别脚本仍是v2。不能只看这些文件就判断最新结果或评价范围。

## 运行方式

从仓库根目录，使用现有项目`.venv`；依赖已安装，无须重新创建环境。

```powershell
# 当前算法，处理30篇，生成_v3输出
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/recognize_v3.py

# 对固定25篇参考标注进行评价
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate_remaining25.py --version v3

# 回归测试
& .venv/Scripts/python.exe -m unittest discover -s experiments/exp02_entity_recognition/tests -v
```

参考标注已冻结，正常复测不需要运行导出脚本或重新标注。若确需修订标注，应单独记录理由，避免与算法变化混在一起比较。

## 后续改进的边界和起点

- 仍有143项名称级漏识，其中POI132项、时间11项。优先查看详细漏识和上下文，继续完善长尾景点及历史别名处理，避免仅堆当前文章词条。
- 这25篇已经用于错误分析和v3迭代，83.79%是开发集结果；参考标注还可能存在遗漏、边界和类型判断偏差。
- **没有完成陌生数据集的独立测试，也没有承诺新数据能达到83.79%。** 同景区新文章可复用规则；新景区还涉及原词典、排除规则以及三景区入口配置的适配。
- 如需验证泛化，先冻结当前v3和词典，用未参与调试的新文章建立参考标注并测量；随后再适配，分别保留适配前后成绩。
- 本侧栏未执行Git提交或推送。工作区还存在主聊天及其他实验的改动，接手时不要整体回退、整体覆盖或把全部工作区内容混成一次提交。

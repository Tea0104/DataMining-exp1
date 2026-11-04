# 游览步骤的实体识别

2026年11月2日的v3开发过程与评价范围见 [交接记录](HANDOFF.md)。本页末尾记录v4景点召回增强版和跨景区入口。

使用 Jieba、自定义词典与规则识别景点 POI、交通方式和时间节点。处理实验一的 selected_v2 数据，按景区输出实体 JSON、词频表和柱状图。技术路线保持不变。

## 环境与运行

已在仓库根目录创建独立 `.venv`，实际验证 Python 3.14.3、jieba 0.42.1、matplotlib 3.11.2。Windows PowerShell 从仓库根目录运行：

```powershell
# 当前环境已安装，后续直接运行
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/recognize_entities.py --version v1
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/recognize_entities.py --version v2
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate.py --version v1
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate.py --version v2

# 语义回归与已生成文件的结构检查
& .venv/Scripts/python.exe -m unittest discover -s experiments/exp02_entity_recognition/tests -v
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/tests/test_entities.py
```

重建环境时用 `uv venv .venv --python 3.14`，再用 `uv pip install --python .venv/Scripts/python.exe -r experiments/exp02_entity_recognition/requirements-lock.txt` 安装本次完整依赖。`requirements.txt` 仍保留两个直接依赖。Jieba 旧版在 Python 3.14 首次加载可能提示转义字符 SyntaxWarning，本次所有入口均可正常运行。

识别参数：`--version {v1,v2}`、`--scenic TAISHAN WULINGYUAN JINGYUETAN`（默认全部）、`--input`、`--outputs`。评估支持 `--version`、`--scenic`、`--outputs`、`--dataset`；`--gold` 必须同时指定一个景区。

## 输入与方法

输入为 `data/processed/full/selected_v2/dataset.json`，30 篇、三个景区各 5 篇官方路线和 5 篇游记。共有 34,064 个非空白字符；JSON 的原文字符长度合计 35,457，包含空白，两种计数不要混用。`clean_text` 不二次清洗。

v1 保留原有后缀和数字规则，作为基线。v2 使用公共词表和分景区词表，共 217 条；每次抽取创建独立 Jieba 分词器，避免版本、景区之间互相污染词典。先按分词识别词典与后缀候选，再识别时刻、时长和行程日，最后统一按最长跨度去冲突。

时间支持“11点半”“十一点半”“9—10点”“23:00-01:40”“十分钟”“4小时30分钟”“第四天”“Day4”“前一天”等；排除费用、年份、非法时刻以及“一点都不累”“近一点”等非时间表达。景区内别名保留原文，以可选 `alias_of` 记录对应全称；“湿地”“滑雪场”等泛称受游览上下文约束。

`start/end` 是 Python Unicode 字符索引，左闭右开，满足 `clean_text[start:end] == text`。每次出现独立保存；交通的 `canonical` 用于类别统计，不能作为图谱节点 ID。

## 当前输出

| 文件 | 说明 |
|---|---|
| `outputs/entities_<景区>_<版本>.json` | 实体及类型、文档、位置、识别方法和可选别名 |
| `outputs/stats_<景区>_<版本>.json` | 分类型、名称与逐篇统计 |
| `outputs/stats_all_<版本>.json` | 三景区汇总 |
| `outputs/entity_freq_<景区>_<版本>.csv/.png` | 词频表和三类 Top10 柱状图 |
| `outputs/evaluation_v1.json`、`evaluation_v2.json` | 分别保存两版名称级评价和带原文位置的差异清单 |
| `outputs/evaluation.json` | 两版评价文件索引，不再相互覆盖 |
| `outputs/entity_spec.md` | 与当前代码同步的类型与边界规范 |
| `outputs/gold_*.json`、`gold_review.md` | 当前127项金标及修订记录；原115项已归档 |
| `outputs/gold_audit.json` | 13项审计修订的原文证据与用户授权合入状态 |
| `outputs/manual_check.md`、`iteration_log.md` | 质量检查及历史迭代记录 |

v1 保持 1192 条；v2 当前为 1471 条，其中 POI 972、交通 245、时间 254。三景区分别为泰山 746、张家界武陵源 453、净月潭 272 条。

## 评价解释与复核状态

用户确认已复核原 `gold_review.md`，并于2026-11-01授权合入13项审计建议：11项补标、1项边界修正（塔楼→月塔楼）、1项别名口径调整（计入橡树岭）。当前金标为127项、5篇文章（3篇官方、2篇游记）；原115项金标和复核记录原样保存在 `archive/gold_before_20261101_corrections/`。授权合入不等于新一轮独立盲标或逐条人工复核。

| 版本 | TP | FP | FN | 精确率P | 召回率R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 30 | 40 | 97 | 0.4286 | 0.2362 | 0.3046 |
| v2 | 127 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |

两版统一对修订后的127项金标评价。v2在这5篇的名称级输出与当前金标完全匹配；词表、规则和金标使用同批语料，100%属于样本内一致性，不代表1471条输出全部经过人工确认，也不代表新景区效果。

评价按“文档＋类型＋表面名称”去重，不评价每次出现的边界；结构检查验证偏移可回溯、无重复无重叠，语义边界另有针对性回归测试，二者都不能替代全量人工语义核验。没有新增实验报告正文。

## 新增25篇参考标注与单独评价

2026-11-02按用户要求补充剩余25篇的助手参考标注，未经人工复核，合计882项（POI510、交通113、时间259）。加上原5篇127项，目前30篇均已有名称级参考标注，但两批复核状态不同。原来的 evaluation_v2.json 仍只评价5篇，不是30篇整体指标。

在新增25篇上，现有v2命中550项、漏识332项，名称级召回率62.36%，精确率95.65%，F1为75.50%；本轮不修改词典、规则或预测。助手参考标注不等同人工金标准，文章也已用于此前词典开发。

结果见 outputs/remaining25_evaluation_summary.md，金标见 outputs/gold_remaining25.json，逐篇、分类型和漏识证据见 outputs/evaluation_v2_remaining25.json。名称清单见 annotations/remaining25_labels.json。

```powershell
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/build_remaining25_gold.py
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate_remaining25.py --version v2
```

## v3算法改进

新增v3，在原词典不变的条件下增加名称边界、路线节点、别名和通用交通时间规则。固定25篇882项参考标注上，名称级召回率由62.36%升至83.79%，精确率由95.65%升至96.98%，F1由75.50%升至89.90%。这25篇用于开发迭代，且金标未经人工复核，不能当独立泛化测试。

v3已处理全部30篇，输出1667条；所有文件带_v3后缀，旧v2和参考标注不变。详细结果见 outputs/v3_improvement.md、outputs/v3_improvement.json 和 outputs/evaluation_v3_remaining25.json。原5篇的v3评价单列 outputs/evaluation_v3_sample5.json。24项回归测试及全量结构/词频校验通过。

```powershell
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/recognize_v3.py
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate_remaining25.py --version v3
```

## v4景点召回增强版

从中文旅游句式提取地点候选。目的地、出发点、活动地点、并列景点、地点介绍句和明确的行程栏都能提供线索。带地点类别词的候选可以在正文里发现，明确的名称栏和带引号的命名句也支持无常见地名后缀的名称。通名、动作和跨实体拼接由筛选规则拦截。新增候选只进入已有实体之外的位置，保留v3的交通、时间和景点边界。

新增规则用虚构景区和空景点词表设计与检查。12组自造句中的21个预期景点均被识别。该结果检查句式和字符位置，真实陌生景区的效果仍需另做人工评价。

| 指标（固定25篇助手参考，名称级） | v3 | v4 |
|---|---:|---:|
| 景点命中数 | 378/510 | 382/510 |
| 景点召回率 | 74.12% | 74.90% |
| 景点精确率 | 95.21% | 92.72% |
| 景点F1 | 83.35% | 82.86% |
| 三类整体F1 | 89.90% | 89.57% |

现有语料上的召回增益为0.78个百分点，同时多出11个未匹配参考的景点名称。两版均复用旧语料开发过的基础规则和词典。25篇参考标注由助手完成。原5篇单独复测，整体F1由98.44%变为97.67%，景点召回率保持100%。结果见 [25篇评价](outputs/evaluation_v4_remaining25.json) 和 [原5篇评价](outputs/evaluation_v4_sample5.json)。

```powershell
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/recognize_v4.py
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate_remaining25.py --version v4
```

跨景区使用识别入口的`--input`和`--outputs`，输入为含`doc_id`、`scenic_id`、`clean_text`字段的JSON记录数组。v4默认从输入读取景区编号。陌生景区使用公共词表和句式规则，排除名单不沿用原三个景区的外部地点设置。默认输出带`_v4`后缀。

## v5 景点规则改进

v5从v3结果继续补景点。新增无引号旧称和别名列表、题刻和短标题、明确的时刻行程与站点栏，并根据名称中心词补全被截短的景点。现有词典沿用，新增识别规则按句式和名称边界判断。规则保留交通和时间输出，只有明确的名称后缀或路线标签边界才可替换旧POI跨度。回归用例使用虚构的书院、旧称、碑刻和路线节点。

| 指标（固定25篇，景点名称级） | v3 | v4 | v5 |
|---|---:|---:|---:|
| 命中参考 | 378/510 | 382/510 | 422/510 |
| 召回率 | 74.12% | 74.90% | 82.75% |
| 精确率 | 95.21% | 92.72% | 95.05% |
| F1 | 83.35% | 82.86% | 88.47% |

相对v3补回44个原漏识名称，新增3个参考未匹配的名称，未损失原已命中的景点名称。例子包括「太平顶」「中天门小广场」和「五岳独尊石刻」。三类整体F1为92.61%，原5篇景点召回率仍为100%，原5篇三类整体F1为98.05%。此轮利用了现有开发语料的误差类型，25篇参考仍为助手标注。 [25篇结果](outputs/evaluation_v5_remaining25.json) · [原5篇结果](outputs/evaluation_v5_sample5.json)

```powershell
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/recognize_v5.py
& .venv/Scripts/python.exe experiments/exp02_entity_recognition/src/evaluate_remaining25.py --version v5
```

全部30篇的实体、统计和词频输出使用`_v5`后缀。新景区可用`--input`和`--outputs`接入含文档编号、景区编号和正文的JSON数据。

# 游览步骤的实体识别

## 新30篇数据的接入提示

项目1已另交付`data/processed/full/selected_v2/dataset.json`，景区编号为`TAISHAN`、`WULINGYUAN`、`JINGYUETAN`，每景区10篇。下面的已有运行结果仍基于原黄山两篇，不因新数据就绪而自动变成全量实验结果。

接入时须同时更换`--input`和`--scenic`，每景区使用独立`--outputs`目录。当前词表仍面向黄山，`summarize`的scenic_id和图表标题也写死黄山，需组员扩充词表并参数化标签后再正式验收；原黄山金标不用于评估新30篇。完整字段和已知问题见[项目1交接说明](../../docs/handoff.md)。

黄山单景区的实体识别初版：识别 **景点 POI、交通方式、时间节点** 三类实体，保留出现位置，做词频可视化并按结果迭代一版。

## 状态与范围

- 只做黄山两条文本：`HS_OFF_001`（官方路线，136 字）、`HS_NOTE_001`（游客游记，2711 字）。
- 故宫、西湖暂不参与：样本质量不足，留给后续扩充数据后再接。
- 这是可运行初版，不是最终交付；报告正文尚未撰写。

## 输入

`data/processed/sample_v1.json`，按 `scenic_id == huangshan` 过滤，统一使用 `clean_text` 字段。
字段约定见 [`docs/data_contract.md`](../../docs/data_contract.md)。

## 依赖

- Python 3.10 及以上
- `jieba`（分词与自定义词典）
- `matplotlib`（词频柱状图，需要中文字体，脚本优先用 `C:\Windows\Fonts\msyh.ttc`）

```bash
pip install jieba matplotlib
```

## 运行

在仓库根目录执行：

```bash
# v1 基线：纯 jieba + 后缀规则，不使用词表与停用词
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v1

# v2 优化：自定义词典 + 停用词 + 数字/行程日规则
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2

# 按名称级金标评估 v1 / v2
python experiments/exp02_entity_recognition/src/evaluate.py
```

可选参数：`--scenic`（默认 `huangshan`）、`--input`（默认 `data/processed/sample_v1.json`）、`--outputs`（默认本实验 `outputs/`）。

## 输出

| 文件 | 说明 |
|---|---|
| `outputs/entities_v1.json` / `entities_v2.json` | 实体记录数组，含 `doc_id`、`text`、`entity_type`、`subtype`、`granularity`、`canonical`、`start`、`end`、`sentence_id`、`method` |
| `outputs/stats_v1.json` / `stats_v2.json` | 每篇的句数、实体数、分类型/分类别计数、唯一名计数、粒度分布 |
| `outputs/entity_freq_v1.csv` / `_v2.csv` | 分类型词频表 |
| `outputs/entity_freq_v1.png` / `_v2.png` | 三类实体 Top10 词频柱状图 |
| `outputs/gold_huangshan.json` | 名称级人工金标（AI 初标，待组员复核） |
| `outputs/evaluation.json` | 两版的分类型 P/R/F1 与误识别、漏识别清单 |
| `outputs/entity_spec.md` | 实体定义规范表（类型、子类型、边界、易混淆对照） |
| `outputs/manual_check.md` | 逐条人工抽查记录与典型错例 |
| `outputs/iteration_log.md` | v1 → v2 的改动、指标变化与未解决问题 |

位置口径：`start`/`end` 为 `clean_text` 的 Python Unicode 字符索引，左闭右开，满足 `clean_text[start:end] == text`。

## 方法要点

1. **分词**：`jieba.tokenize` 拿到带偏移的 token；v2 起先把 `config/lexicon.json` 写入自定义词典，保证长实体不被切碎。
2. **匹配顺序**：词表命中 → 闭类词（时间词、交通泛称）→ 后缀规则；重叠时**长实体优先**，同跨度按 `POI > TRANSPORT > TIME` 取值。
3. **数字时刻**：v1 三位或四位数字即判为时刻；v2 要求四位、在合法时刻范围、且后文不含价格/长度/年龄量词。
4. **可视化迭代**：先看 v1 词频图，发现“西海/宾馆/索道”霸榜是碎片与通名，再补词典与停用词，v2 复查。
5. **粒度分层**：具名线路（云谷索道、玉屏索道）保留 `text` 与位置，另加 `canonical` 上位类别和
   `granularity`（`specific` / `generic` / `unknown`）。`canonical` **只能用于统计与 Schema 分层，不能当节点 ID**，
   否则上山与下山两条索道会被合并。泛称“索道”指向哪条线路属于共指问题，留给项目 4。

## 结果摘要（黄山两条文本）

| 版本 | mention | POI / 交通 / 时间（唯一名） | 总体 P | 总体 R |
|---|---:|---|---:|---:|
| v1 | 97 | 23 / 7 / 8 | 0.43 | 0.36 |
| v2 | 100 | 31 / 10 / 7 | 0.98 | 0.98 |

v2 仍残留 1 处错误：`小火车` 被识别成 `火车`。评估口径的局限见 `outputs/iteration_log.md` 第 4 节。

交通方式按类别汇总（`stats_v2.json` 的 `by_canonical`）：索道 16 次（具名 6 + 泛称 10）、大巴 2、自驾 2、面包车 1、火车 1、徒步 1。具名索道不并入泛称，见 `outputs/iteration_log.md` 第 6 节。

## 目录

```text
exp02_entity_recognition/
├── src/
│   ├── recognize_entities.py   实体识别主程序（v1 / v2）
│   ├── evaluate.py             名称级 P/R/F1 评估
│   └── config/
│       ├── lexicon.json        实体词表与子类型定义
│       └── stopwords.json      停用词、片段拦截、数字上下文
├── outputs/                    结果、图表、规范表、抽查与迭代记录
└── README.md
```

## 已知限制

- 只有 2 条文本、2847 字、55 个金标名，不能据此估计泛化性能。
- 金标与词表同源，v2 的绝对指标偏乐观；可比较的主要是 v1 → v2 的提升。
- 词表只覆盖黄山，换景区需要扩充 `config/lexicon.json` 与 `stopwords.json`。

## 协作约定

公共数据接口见 [`docs/data_contract.md`](../../docs/data_contract.md)。保留 `doc_id` 与来源；
方法、人工核验和真实失败案例需同步写入报告。本目录目前为初版实现，尚未完成报告与全量数据验证。

# 游览步骤的实体识别

三景区（泰山、张家界武陵源、净月潭）的实体识别：识别 **景点 POI、交通方式、时间节点** 三类实体，
保留 `clean_text` 字符位置，按景区输出词频图，并用 v1/v2 两版记录一次规则迭代。

## 状态与范围

- 数据：`data/processed/full/selected_v2/dataset.json`，30 篇（每景区 5 篇官方路线 + 5 篇游记），34,064 个非空白字符。
- 原黄山 6 条样本（`sample_v1`）的产物已归档到 [`archive/sample_v1_huangshan/`](archive/sample_v1_huangshan/)，不参与本轮统计。
- 本轮 **没有金标**，因此不输出精确率/覆盖率，只给抽样人工核对（见 `outputs/manual_check.md`）。

## 输入

`data/processed/full/selected_v2/dataset.json`，按 `scenic_id` 过滤，统一使用 `clean_text`。
字段见 [`docs/data_contract.md`](../../docs/data_contract.md)。

## 依赖

- Python 3.10 及以上
- `jieba`（分词与自定义词典）
- `matplotlib`（词频柱状图；脚本优先加载 `C:\Windows\Fonts\msyh.ttc`，缺失时回退 `SimHei`）

```bash
pip install jieba matplotlib
```

## 运行

在仓库根目录执行：

```bash
# v1 基线：只靠后缀与数字规则，不使用词表与停用词
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v1

# v2：公共+景区词表、停用词、显式时刻规则
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2

# 只跑一个景区
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2 --scenic TAISHAN
```

参数：`--version {v1,v2}`（默认 v2）、`--scenic`（可多个，默认 `all`）、`--input`、`--outputs`。

## 输出

| 文件 | 说明 |
|---|---|
| `outputs/entities_<景区>_<版本>.json` | 实体记录，含 `doc_id`、`text`、`entity_type`、`subtype`、`granularity`、`canonical`、`start`、`end`、`sentence_id`、`method` |
| `outputs/stats_<景区>_<版本>.json` | 分类型/分类别计数、唯一名、粒度分布、逐篇统计 |
| `outputs/stats_all_<版本>.json` | 三景区汇总 |
| `outputs/entity_freq_<景区>_<版本>.csv` | 分类型词频表 |
| `outputs/entity_freq_<景区>_<版本>.png` | 三类实体 Top10 柱状图 |
| `outputs/entity_spec.md` | 实体定义规范表 |
| `outputs/manual_check.md` | 抽样人工核对 |
| `outputs/iteration_log.md` | v1 → v2 迭代记录 |

位置口径：`start`/`end` 为 `clean_text` 的 Python Unicode 字符索引，左闭右开，满足 `clean_text[start:end] == text`。

## 方法要点

1. **分层词表**：`config/lexicon.json` 分公共层（37 词，跨景区复用）与景区层（163 词），共 200 条；v2 写入 jieba 自定义词典。
2. **匹配顺序**：词表 → 闭类时间词 → 停用词拦截 → 高精度后缀兜底（11 个后缀、≥3 字）；重叠时长实体优先。
3. **时刻规则**：v1 把三位或四位数字都判为时刻，把门票价、年份、台阶数误收；v2 只认 `4:13`、`23:00`、`9点54分` 这类显式格式。
4. **粒度分层**：具名线路（天子山索道、百龙天梯）保留 `text`，另加 `canonical` 上位类别；`canonical` 不可当节点 ID。
5. **可视化迭代**：先跑 v1 看词频图，发现碎片与数字噪声后再补词典与规则。

## 结果摘要

| 版本 | mention | POI | 交通 | 时间 | 泰山 POI 唯一名 |
|---|---:|---:|---:|---:|---:|
| v1 | 1192 | 806 | 227 | 159 | 145 |
| v2 | 1334 | 949 | 236 | 149 | 95 |

v2 的 POI 唯一名减少而 mention 增加，说明碎片被合并为完整实体；时间从「门票价/年份」变为真实行程时刻。

## 目录

```text
exp02_entity_recognition/
├── src/
│   ├── recognize_entities.py   实体识别主程序（v1 / v2，支持多景区）
│   ├── evaluate.py             名称级评估（需自备金标，本轮未使用）
│   └── config/
│       ├── lexicon.json        公共词表 + 三景区词表
│       └── stopwords.json      通名、景区片段、跨景区地点
├── outputs/                    结果、图表与三份说明
├── archive/sample_v1_huangshan/  原黄山样本的产物与词表（历史版本）
└── README.md
```

## 已知限制

- 无金标，未计算 P/R；抽样 36 条只能发现明显问题。
- 词表为人工整理，未覆盖全部长尾景点（如 `徒步惊喜`、`黄龙洞`）。
- 带数字的时长（`4--6小时`）未整体标注，见 `outputs/entity_spec.md` 第 6 条。
- 抽样核对与规范表仍为助手初稿，需组员复核签字。

## 协作约定

公共数据接口见 [`docs/data_contract.md`](../../docs/data_contract.md)。保留 `doc_id` 与来源；
方法、人工核验和真实失败案例需同步写入报告。本目录为初版实现，报告正文尚未合并。

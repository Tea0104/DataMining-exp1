# 黄山样本实体识别产物（历史归档）

这里保存的是 `sample_v1`（黄山 `HS_OFF_001` + `HS_NOTE_001`）单景区版本的产物，**不参与 selected_v2 的统计与验收**。

## 为什么保留

- `sample_v1` 仍留在 `data/processed/`，字段与 selected_v2 兼容；
- 这套产物证明同一套代码框架在单景区小样本上跑通过，换数据只需替换词表与参数；
- 其中 `evaluation.json` 是唯一一次带**名称级金标**的评估（55 项，v1 0.43/0.36 → v2 0.98/0.98）。

## 内容

| 文件 | 说明 |
|---|---|
| `entities_v1.json` / `entities_v2.json` | 97 / 100 条实体记录 |
| `stats_v1.json` / `stats_v2.json` | 分类型统计 |
| `entity_freq_v1.csv` / `_v2.csv` | 词频表 |
| `entity_freq_v1.png` / `_v2.png` | 词频图 |
| `gold_huangshan.json` | 55 项名称级金标 |
| `evaluation.json` | 两版 P/R/F1 与误漏清单 |
| `entity_spec.md` | 当时的单景区规范表 |
| `manual_check.md` | 当时的逐条抽查 |
| `iteration_log.md` | 当时的 v1 → v2 记录 |
| `config/lexicon.json`、`config/stopwords.json` | 当时的黄山词表与停用词 |

## 注意

- 这批评分口径与 selected_v2 不同：金标与词表同源，0.98 是上限值而非泛化准确率。
- 当时的代码版本见 git 历史（提交 `ebb9bcb` 及之前），当前 `src/` 已改为多景区版本，不能直接用这份 config 复现新数据。

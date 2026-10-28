# 正式文本数据接口（selected_v2）

`data/processed/full/selected_v2/dataset.json`为30条记录的JSON数组；同目录`dataset.jsonl`每行一条相同记录，均为UTF-8。原`sample_v1`六条开发样本保留，基础字段兼容。

| 字段 | 类型 | 说明 |
|---|---|---|
| doc_id | string | 稳定唯一的文档编号，不因清洗或排序重排 |
| scenic_id / scenic_name | string | TAISHAN、WULINGYUAN、JINGYUETAN及对应景区名 |
| text_type | string | official_route或tourist_note |
| title | string | 原文章标题，范围选择单独记录 |
| source_url / publisher | string | 原文地址及发布机构或网站 |
| author | string/null | 来源记录的作者，未知留null |
| published_at | string/null | 明确日期依据，优先详情发布标签；未知留null |
| collected_at | string | 原始采集时间，含时区 |
| content_scope | string | reviewed_scenic_scope_from_article |
| raw_text | string | 所选景区范围的未归一化文字，保留原表述 |
| clean_text | string | 项目2—5统一使用的文本 |
| license / license_url | string / string或null | 来源权利说明及明示许可链接，不自动授予其他权利 |
| notes | string | 范围、原文疑点和使用限制 |
| blocks | array | 原网页块编号、角色、XPath、text及start/end |
| metrics | object | 完整正文、取用范围、清洗后的非空白字数及规则命中 |
| date_candidates / published_at_basis / date_conflict | array / string / bool | 日期候选、所选依据与冲突 |
| review_flags / content_issues | array | 范围标记和原文待核问题 |
| source_response_sha256 / source_raw_text_sha256 | string | HTML响应与完整采集正文哈希 |
| raw_scope_sha256 / clean_text_sha256 | string | 选取范围及清洗文本哈希 |
| duplicate_of | null或string | 本批均为null；发现全文重复时验收失败，不悄悄删到不足5+5 |
| processing_scope / scope_version | string | text_only及范围配置版本 |

`raw_text`不是完整跨城游记。完整采集内容位于`data/raw/full/selected_v2/`；逐块去留位于正式输出的`audit/`。未读取图片内容或alt补充正文。块不是句子或路线步骤，块角色和偏移不是实体/关系标注。

## 最小读取

```python
import json
from pathlib import Path

root = Path(__file__).resolve().parents[3]  # 代码在experiments/<实验>/src/时
records = json.loads((root/'data/processed/full/selected_v2/dataset.json').read_text(encoding='utf-8'))
for record in records:
    doc_id, text = record['doc_id'], record['clean_text']
```

## 下游约定

保留`doc_id`、`scenic_id`及原文证据。位置为Python Unicode字符索引，左闭右开`[start,end)`，满足`clean_text[start:end] == evidence`，不能用UTF-8字节或JavaScript UTF-16长度替代。

- 项目2：实体含text、entity_type、start、end；原名与归一化名分开。
- 项目3：步骤、景点、活动、时间分别记录，未知时间null，推断另标inferred；区分计划、实际、未到访和折返。
- 项目4：人工标注与算法预测分开，精确定位代词；允许没有明确先行词。
- 项目5：条件和建议保留证据位置，普通建议不必然有条件，未出现的条件不补写。
- 项目6：合并节点/边仍保留来源、原名及归一化名。

本批未提供实体、路线、共指或条件关系金标准。触发词计数、示例词表及格式检查通过率不能当作人工标注或抽取准确率。各模块另行交付方法、结构化结果、真实人工检查和失败案例。

# 开发样本质量检查

数据版本：sample_v1。3 个景区、6 条文本，各有 1 条官方路线和 1 篇游客游记的选定正文。

| 文本编号 | 景区 | 类型 | 原始字符数 | 清洗后字符数 |
|---|---|---|---:|---:|
| GG_NOTE_001 | 故宫博物院 | tourist_note | 424 | 336 |
| GG_OFF_001 | 故宫博物院 | official_route | 255 | 227 |
| HS_NOTE_001 | 黄山风景区 | tourist_note | 3001 | 2711 |
| HS_OFF_001 | 黄山风景区 | official_route | 140 | 136 |
| XH_NOTE_001 | 杭州西湖风景名胜区 | tourist_note | 654 | 574 |
| XH_OFF_001 | 杭州西湖风景名胜区 | official_route | 88 | 78 |

## 完整性检查

- six_records：通过
- three_scenic_areas：通过
- one_official_and_one_tourist_per_scenic：通过
- unique_doc_ids：通过
- required_fields_nonempty：通过
- no_exact_duplicate_clean_text：通过
- no_replacement_characters：通过
- no_html_or_script_noise：通过
- no_body_urls：通过
- normalization_idempotent：通过

## 使用限制

- 开发样本，不是完整实验语料或独立评估集。
- 黄山官方及西湖官方转载来源使用搜索索引核验片段，直接访问分别遇到HTTP 412和脚本校验页。
- 西湖官方来源是官方发布内容的新闻网站转载，已与官网第一手来源区分。
- 路线和游客游记取用范围不完全相同；时间、条件、共指样本分布不均。
- 诊断命中数只是触发词计数，不是实体、共指标注数量或抽取准确率。
- 原文误字、口语、图注、未到访地点和周边地点保留，需后续模块判断。

清洗剥离HTML标签、过滤脚本和样式、移除正文网址、归一化换行空白及技术性控制符。来源URL保留在元数据，raw_text保留原始正文网址。景点原名、时间、条件、代词、序号和路线连接符保持原文，不自动补写或纠错。

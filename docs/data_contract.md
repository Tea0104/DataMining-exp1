# 开发样本数据接口

## 输入文件

`data/processed/sample_v1.json` 是 JSON 数组；`sample_v1.jsonl` 每行一条相同记录。文件采用 UTF-8 编码。

| 字段 | 类型 | 说明 |
|---|---|---|
| doc_id | string | 稳定且唯一的文本编号，不因清洗或排序而改变 |
| scenic_id | string | 景区固定编号 |
| scenic_name | string | 景区名称 |
| text_type | string | `official_route` 或 `tourist_note` |
| title | string | 来源文章标题，取用章节另行记录 |
| source_url | string | 可核验的原始来源链接 |
| publisher | string | 发布机构或网站 |
| author | string/null | 已核验作者；未知为 null |
| published_at | string/null | 来源明确标示的发布日期；未知为 null |
| collected_at | string | 采集时间，含时区 |
| content_scope | string | 正文全文、路线章节或指定游记片段 |
| raw_text | string | 所选取用范围的未归一化正文，保留原有表述 |
| clean_text | string | 后续抽取统一使用的文本 |
| license | string | 来源许可或取用说明，不自动授予其他权利 |
| license_url | string/null | 来源明示的许可链接 |
| notes | string | 取用范围、原文疑点、历史时效与其他限制 |

## 最小读取示例

```python
import json
from pathlib import Path

root = Path(__file__).resolve().parents[3]  # 代码位于 experiments/<实验>/src/ 时
records = json.loads((root / 'data/processed/sample_v1.json').read_text(encoding='utf-8'))
for record in records:
    doc_id = record['doc_id']
    text = record['clean_text']
    # 在这里调用本实验处理函数。
```

也可以从仓库根目录运行脚本，显式传入输入文件路径，避免依赖当前工作目录。

## 输出约定

所有模块保留 `doc_id`、`scenic_id`；实体编号和来源编号不能只在当前文件中临时重排。

- 项目 2：实体记录含 `doc_id`、`text`、`entity_type`、`start`、`end`。位置应满足 `clean_text[start:end] == text`。
- 项目 3：路线记录含步骤顺序、景点、活动、时间。未知时间用 `null`；推断时间另标 `inferred`，不要伪装成原文信息。
- 项目 4：分开保存人工标注和算法预测，以精确位置区分同句中的重复代词。没有明确先行词的案例允许为空。
- 项目 5：条件与建议保留原文证据和位置。普通建议不必然含条件，未出现的条件不补写。
- 项目 6：保留节点、边的来源，合并名称时保留原名与归一化名。

## 开发与评估

这 6 条记录是模块开发输入，未预先提供实体、共指或条件关系的金标准。触发词计数、示例词表等只能用于诊断，不能当作人工标注或准确率。

模块完成后交付源码、结构化结果、运行说明、人工检查和真实错误案例。完整语料扩充时沿用本接口，并单独划分后续评估样本。

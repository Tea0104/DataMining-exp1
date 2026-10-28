# 项目3路线输出接口

入口为 `outputs/routes_huangshan.json`，Schema版本 `1.1`。公共输入约定见 `../../docs/data_contract.md`。

## 来源和项目2输入

默认 `entity_source=exp02_entities_v2`、`exp02_integration_status=integrated_position_validated`。显式选择dictionary模式才使用独立开发词表，不会在默认模式静默补词。

`upstream_entities` 保存实体文件名、字节SHA256、100个实体的分类型／分文档数量与位置校验状态。`source_entities` 保存带来源ID的项目2原始字段。每条来源ID为 `doc_id:entity_type:start:end`；原文名称去空白用于规范名，`canonical` 仍是类别属性，不能作身份。

`input_sha256` 为共享输入文件字节哈希，`clean_text_sha256` 为各正文UTF-8字节哈希，`config_sha256` 为独立基线配置哈希。位置校验仅证明切片对齐，不证明语义正确或无漏抽。

## 路线类型

各路线保留 `route_id/doc_id/scenic_id/scenic_name/source_url/text_type`。

| route_kind | 含义 |
|---|---|
| official_recommended | 官方主线；条件支线和远观另存 |
| tourist_observed | 游客叙述中有明确活动线索的规则候选，未验收完整实际轨迹 |
| tourist_declared | 作者列表报告的顺序，排除同日明确未前往的节点 |

`steps` 为主线步骤，`optional_branches` 为条件支线，`non_main_mentions` 为远观、假设、周边、边界歧义和回顾性引用等，`excluded_steps` 保留被否定节点及冲突证据。

## 步骤与实体引用

| 字段 | 含义 |
|---|---|
| step_id / order | 同一输入下稳定的步骤标识和文本顺序；新增步骤可能导致编号变化 |
| poi / surface / entity_type | 规范名、原表述、本模块节点类型；无名活动和交通选择的poi为空 |
| activity_label / activity | 简短活动标签／原文活动片段，完整证据可核对 |
| mention_span | 原始正文中实体的Python字符区间，切片等于surface |
| source_entity_id | 主候选对应的项目2mention；无名活动或选择节点为空 |
| context_entity_ids | 证据片段中所有上游实体，仅表示上下文共现 |
| transport_entity_ids | 该片段中的交通实体，不等于全部实际乘坐或已完成共指 |
| time_entity_ids | 该片段中的TIME实体，可能没有分配给本步骤 |
| assigned_time_entity_ids | 实际用于本步骤时段或时刻的局部分句TIME引用 |
| day / time_period | 相对天数／morning、noon、afternoon、evening或unknown |
| time / duration_minutes | 有直接时刻时可为21:00；停留时长缺失则为空，行程两天不能填入 |
| time_expression / time_basis / inferred | 上游时间表达、同分句依据或未知；本版本不推断时间 |
| visit_status / extraction_rule | 规则状态和判定依据，不是人工语义准确性标注 |
| evidence | doc_id、start、end、text，必须与clean_text精确切片一致 |

`additional_evidence` 保存相邻同名步骤被合并后的其他证据。不同天数或明确返回不按名字全局去重。`confirmed` 仅表示有叙述触发线索。`boundary_ambiguous` 需复核原文复合名称，不能作为已到访地点。

## 选择 支线和时间上下文

交通选择有 `choices/choice_mentions/choice_semantics=choose_one`，两个索道选项不能导入为连续步骤。每个选项仍指向独立来源实体。

条件支线有 `branch_id/anchor_poi/anchor_step_id/condition/steps/evidence`，支线步骤有独立ID；`return_to_anchor=true` 表示返回主线锚点。远观对象不进入必经主线。

`time_hierarchy` 为相对天数→periods→step_id列表，每个主线步骤恰好归入一个时段。未知组不代表晚于已知组，整体顺序读order。`temporal_context` 保留上游TIME的文档级背景，包括没有分配到步骤的时长和相对日，不自动构造新活动。

当晚入住等表达仅支持活动上下文时段，不精确证明到达酒店的时刻。来源没有时刻的步骤仍为空。第二天21:00的终点活动不附加虚构目的地。

## 项目6接入约束

图谱应为不同路线保留独立步骤节点，再关联规范实体，来源mention用source_entity_id回查。类别canonical相同的云谷索道、玉屏索道仍是不同实例；泛称索道不由本模块强行消解为线路。

order为文本组织顺序，不证明地理道路连通。列表排除一线天后，前后两点也不能直接认定有直达道路。未验收叙述候选保留状态和证据。

对比指标移除交通、无名活动和周边实体；覆盖/Jaccard用集合，LCS保留序列中的重复。共同地点不足2个时，共同地点顺序一致性为空。可选支线未并入主线指标。

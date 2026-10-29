# Task3 游览路线的层级结构挖掘 考核项自检验收文档

## 1. 任务基础信息

### 1.1 实验目标与审阅口径

- **实验目标（任务书原文）**：挖掘出游览路线的层次结构，理解官方指南与游客游记中路线组织的差异。
- **对应科研点（任务书原文）**：面向程序性文本的层级结构挖掘技术。
- **任务与依据**：本次审阅对象为实验项目3，评分依据为[Final任务书](../docs/rubrics/《数据挖掘》探索性实验任务书及评分细则【Final】.docx)中该项目的完整评分表。
- **审阅信息**：审阅用户提供的本地已有完成代码及已保存产物。仓库根目录为 `D:/数据挖掘/DataMining-exp1`，本地分支为 `feat/exp02-entity-recognition`，基础提交为 `4a16120643181f1615e85476604aa7aceafb1796`；项目3属于已有未提交工作区内容，不能把基础提交SHA当作项目3已提交版本。
- **审阅阶段操作边界**：只读取源码、配置和已有结果；执行已有测试及不写出结果的合成诊断调用；仅新增本验收MD。没有修改、补全或重构源码，没有新增实验功能、补充语料、覆写现有输出或提交PR。
- **文档参考**：用户提供的《实验一逐项验收说明》仅用于参考验收表述。其泰山、张家界、净月潭30篇数据和验证数字不属于本项目3的证据，未移用。
- **结论含义**：【已完成】指现有实现能够支撑该条要求；【部分完成】指有实现，但存在本条相关缺陷或验收证据不足；【未完成】用于完全没有相应逻辑。结论不是人工最终给分，也不将测试通过率当作语义准确率。

**评分表口径须保留原样。** 基础四项为40＋40＋10＋10＝100分。官方与游客路线对比被列为附加题，分数栏写20分，但三个细目分别为8、12、10分，合计30分；原表同时规定该实验最高100分。本文件逐字保留所有分值，不擅自折算，具体附加分换算由教师确认。

本文件保留提交前只读审阅时的评分原文、结论和代码指纹；仓库发布时仅整理链接与阶段说明，所列缺陷没有在本次提交中修复。

### 1.2 实际代码与技术栈

| 部分 | 当前代码及定位 | 审阅范围 |
|---|---|---|
| 路线解析、层级及导出 | [route_hierarchy.py][route_src]，`Extractor`、`compare`、`run` | 实际抽取逻辑和输出，不以README的能力概述替代源码 |
| 项目2实体接入 | [entity_source.py][entity_src]，`EntityIndex`、`clause_span` | 位置、类型、粒度、天数、局部时间关联 |
| 静态绘图 | [plot_hierarchy.py][plot_src]，`plot` | PNG、SVG的实际生成及适用范围 |
| 独立开发词表 | [huangshan_pois.json][config] | 显式dictionary模式使用的名称与别名；默认exp02模式不据此补词 |
| 回归测试 | [test_route_hierarchy.py][tests_core]、[test_exp02_integration.py][tests_exp02] | 17项核心测试与11项接入测试 |
| 既有说明材料 | [README][readme]、[SCHEMA][schema]、[实验报告][report] | 与代码和结果交叉核对，不把说明中的结论自动认定为事实 |

- **语言与标准库**：Python；解析代码直接使用 `argparse/csv/hashlib/html/json/pathlib/re`，实体接入使用 `collections.Counter`；测试另使用 `contextlib/io/sys/tempfile/unittest`。
- **第三方库**：绘图脚本直接导入 `matplotlib`、`matplotlib.pyplot`、`font_manager`、`FancyBboxPatch`。项目3读取现成实体时不导入jieba；只有重跑项目2时才需要jieba。已有[依赖文件][requirements]记录jieba 0.42.1和matplotlib 3.11.2，本机环境为Python 3.12。
- **模型与Prompt**：现有项目3未调用LLM或其他预训练模型，没有模型权重、API密钥或Prompt。
- **数据来源**：读取仓库既有开发样本，项目3没有自行采集。仓库[数据说明][data_readme]记录黄山官方线路摘录及真实博客游记章节，不应仅因任务书允许教师数据，就把它改称已核验的教师发布数据集。
- **实际使用规模**：`HS_OFF_001`官方路线136字符；`HS_NOTE_001`游记2711字符。项目2的v2文件共100条mention：POI 65、TRANSPORT 23、TIME 12。其他景区不进入本次项目3输出。
- **定义与Schema**：`route_kind`区分官方推荐、游客叙述事件和游客报告列表；`PERIODS`定义morning/noon/afternoon/evening/unknown；`visit_status`区分推荐、规则叙述线索、列表报告、支持证据及排除状态。具体字段与来源ID见[SCHEMA][schema]。这些状态不是人工金标。

本次审阅开始时记录了23个已有源码、配置、结果及说明文件的SHA256，用于结束时确认未改动。关键源码指纹为：`route_hierarchy.py: fbdfbaabe7ba…`、`entity_source.py: 8460023224e1…`、`plot_hierarchy.py: 7f5242397708…`。实体文件完整SHA256为 `29a5a6111a034e19e4a22be46d7ec2dac9f7d7c1756dbca421f4c7e55ff87691`。

### 1.3 输入及全部已有产出文件

以下链接均指向本次实际审阅的本地文件。命令中使用仓库相对路径，便于从仓库根目录复现。

| 角色 | 文件 | 用途及生成方式 |
|---|---|---|
| 直接输入 | [sample_v1.json][input] | `run`批量读取，再按huangshan筛选 |
| 直接输入 | [entities_v2.json][entities] | 默认exp02模式读取上游100条实体 |
| 直接输入 | [huangshan_pois.json][config] | 两种模式均先加载和校验景区；名称匹配主要用于dictionary模式 |
| 核心输出 | [routes_huangshan.json][routes] | `run`生成；Schema 1.1、三类路线、证据、来源实体、层级与支线 |
| 平表输出 | [route_steps.csv][csv] | `run`生成；UTF-8 BOM，35个主线活动／步骤记录，不含支线与排除项的完整展开 |
| 层级展示 | [hierarchy.html][html] | `render_html`生成；按天与时段组织，可展开原文证据 |
| 静态图 | [hierarchy.png][png]、[hierarchy.svg][svg] | 需另运行`plot_hierarchy.py`，不由主解析入口自动生成 |
| 对比输出 | [comparison.json][comparison] | `compare`及`run`生成；两组官方—游客比较、公式与解释边界 |
| 核验中间件 | [review_cases.json][review] | 条件支线、非主线提及、歧义和排除节点清单；没有人工判定字段或签字结论 |
| 接入检查 | [integration_report.json][integration] | 实体哈希、数量、位置检查及已知上游问题；不是语义评估文件 |
| 运行摘要 | [summary.json][summary] | 三类路线的步骤数、支线数、排除项与检查状态 |
| 既有手写说明 | [README][readme]、[SCHEMA][schema]、[exp03_huangshan.md][report] | 运行、字段、结果解释；并非脚本每次自动生成 |

已有默认结果为：官方14步、游客叙述12步、游客列表9步，共35个主线步骤；另有1条条件往返支线和1个被否定的列表节点。三类路线的“步骤”既含地点，也含交通选择、无名交通活动及行程结束，不得把35直接称为35个独立景点。

## 2. 评分细则逐条审阅校验

### 2.1 官方路线模式分析与结构化解析（40分）

### 2.1.1 路线文本描述模式分析（10分）

>【评分条款原文】：1）能够分析不同路线文本的描述模式（如箭头链路、编号列表、按时间分段等）（10分）；
>
>【完成情况结论】：【已完成】已有代码、测试和说明区分箭头链路、编号列表和叙述线索；实际黄山官方样本只验证了箭头与叙述混合格式。
>
>【代码审阅解析】
> ①定位：[Extractor.official][official]的编号正则与`format`选择、[split_top_level][split]的括号深度和`ARROW`、[Extractor.tourist][tourist]的列表／叙述分流；[编号测试][number_test]及[既有报告][report]“官方路线”部分。
>
> ②边界解析：识别的箭头为`->、→、——、—>、⇒`；编号要求行首数字后跟`.、、．`之一。游客句子有至少2个箭头时进入列表路径；没有独立的通用“时间段标题继承器”，因此不能声称所有按上午／下午分段文本已覆盖。
>
> ③方案取舍：采用显式句法模式，解释成本低，能区分括号内支线与主线箭头；代价是格式覆盖依赖正则，未知连接符、中文序号或自由叙述不保证解析。此条认可的是已有模式分析，后续解析缺陷在2.1.3独立判定。
>
>【核验证据】
>输入核验：在[官方文本所在共享JSON][input]查找排云亭→西海大峡谷北入口等连接及括号支线；在[游记及实体][entities]对应原文查找第二天箭头列表。
>已有输出：官方`format=arrow_narrative`，游客分别为`narrative_rules/arrow_list`，保存在[路线JSON][routes]。合成编号输入“1. 上午游览始信峰\n2. 下午游览光明顶”由已有测试验证；它不是新增真实语料。
>人工验收：在报告中放置两种真实文本片段及模式标记，另明确标注编号示例为合成测试。不可把合成编号测试写成已采集第二份官方路线。

### 2.1.2 统一结构化表示（15分）

>【评分条款原文】：2）设计统一的结构化表示，至少包含步骤/时间/景点/活动等核心字段（15分）；
>
>【完成情况结论】：【已完成】步骤、时间、景点／活动和顺序等核心字段已有明确结构，并保留来源证据和未知值。
>
>【代码审阅解析】
> ①定位：[Extractor.step][step]定义`poi/activity_label/activity/day/time/time_period/duration_minutes/visit_status/evidence`；[Extractor.finalize][finalize]定义`step_id/order/time_hierarchy`；[EntityIndex.mentions][mentions]保留类型与来源ID；[SCHEMA][schema]列出接口。
>
> ②边界解析：无名活动或二选一交通节点允许`poi=null`，实际活动原文仍保留。`time=null`表示没有可靠时刻；第二天行程结束可为21:00。`duration_minutes`在现有实现中始终为空，不代表计算了停留时长。`source_entity_id`为空的无名活动通过上下文实体和句子证据关联。
>
> ③方案取舍：统一字典结构方便项目6读取，显式空值避免编造时间。代价是`activity`主要为原句／片段，不是经过语义拆分的动作标签；存在字段并不证明其业务值已经人工核实。
>
>【核验证据】
>已有输入与输出：官方索道二选一保留`choices`，天海支线保留`anchor_step_id`；游客行程结束记录`day=2、time=21:00、poi=null`。均可在[路线JSON][routes]核对，[CSV][csv]提供主线平表。
>人工验收：逐项检查步骤序号、时间、地点与活动是否存在；任取一个命名步骤，用`mention_span`切片比对`surface`，再用`source_entity_id`查顶层`source_entities`。报告应展示一条地点步骤、一条交通选择和一条含未知值的步骤样例。

### 2.1.3 解析程序与结构化导出（15分）

>【评分条款原文】：3）编写解析程序并输出JSON/CSV等结构化结果，可处理至少1-2种典型格式（15分）。
>
>【完成情况结论】：【部分完成】箭头和完整编号列表可解析并导出JSON/CSV，但混合编号和嵌套条件括号会漏步骤或错误提升支线。
>
>【代码审阅解析】
> ①定位：[Extractor.official][official]中`numbered`、`chunks`、`main`；[parenthetical_spans][parens]仅匹配非嵌套括号；[run][run]与`write_json/csv.DictWriter`负责导出。
>
> ②边界解析：编号模式标签用`len(numbered)>=2`，实际分段却用`if numbered`。只命中1个编号行也会只处理该行，丢弃其他未编号行。嵌套括号仅提取内层括号，外层条件及其实体可能进入主线；括号深度切分并不等于完整嵌套语义解析。
>
> ③方案取舍：确定性分段适合现有短样本，但编号检测与分段条件不一致，括号内容提取未构建嵌套结构。建议方案：统一模式判定条件，保留并解析未编号段；使用括号栈建立区间树，按条件作用域提取支线。本次仅记录方案，不修改代码。
>
>【核验证据】
>本次合成诊断C1：“1. 上午游览始信峰\n下午游览光明顶”，直接调用现有`official`只输出始信峰，未输出光明顶。
>诊断C2：“天海（如体力允许（例如晴天），先上光明顶，再返回天海）→海心亭”，实际主线为天海、光明顶、天海、海心亭，`optional_branches=0`。
>这些诊断使用现有dictionary方式提供名称，调用与默认模式相同的核心分段函数；不写入共享语料或覆盖[正式输出][routes]。正常真实样本仍有14／12／9步，不能因缺陷案例而声称当前正式文件生成失败。
>人工验收：先确认正常JSON/CSV可读，再按C1/C2核对漏项与支线作用域。报告应同时呈现正常导出与失效输入，不仅展示成功截图。

### 2.2 时间维度层级结构构建（40分）

### 2.2.1 时间层级构建（15分）

>【评分条款原文】：1）基于解析结果构建上午/中午/下午或等价的时间层级（15分）；
>
>【完成情况结论】：【部分完成】相对天数和五类时段层级已建立，但官方时间全部未知，且时钟到时段的边界规则存在错误。
>
>【代码审阅解析】
> ①定位：[PERIODS与Extractor.finalize][finalize]、[EntityIndex.day_at][day]、[EntityIndex.period][period]、[EntityIndex.time_for_step][time_step]和`clause_span`。默认模式实际使用项目2TIME；dictionary模式另有句内正则。
>
> ②边界解析：默认仅将同一局部分句中、能归为单一时段的TIME分配给步骤；存在冲突或无时间则为unknown。天数只显式支持T+N和“第二天”，其他行程日表述不会自动泛化。`period`对合法钟点按hour<11归上午，包含00:30等凌晨时刻。
>
> ③方案取舍：保留未知值比按顺序填造时段更忠实原文，局部分句可减少时间误传；代价是跨句时间继承较弱，且现有时段阈值把凌晨并入上午。建议补充夜间／凌晨区间和更多行程日规则，跨句关联需保存依据与置信度，不能直接猜填官方时段。
>
>【核验证据】
>已有统计：官方14步均unknown；游客叙述12步中morning=1、evening=2、unknown=9；游客报告9步均unknown。35步共32步时间未知，来源不足不能由代码自行补成完整上午／中午／下午安排。
>正常证据：第二天行程结束为21:00，来源是项目2的“晚上”“2100”；见[路线JSON][routes]及[接入报告][integration]。
>本次诊断C4：调用现有`EntityIndex.period({text:'0030', subtype:'clock'})`返回morning，说明凌晨边界缺陷；它是合成诊断，不是当前真实数据中的错误时刻。
>人工验收：逐个核对已知时段的原文修饰范围，尤其“当晚要入住”不能等同于精确到达时刻；报告应展示时间层级JSON、未知比例和21:00来源，不把空组当作已有时间分配。

### 2.2.2 景点 活动及先后关系合理性（13分）

>【评分条款原文】：2）层级中景点、活动及先后关系组织合理（13分）；
>
>【完成情况结论】：【部分完成】已区分选择、条件往返、远观及未到访，但同日事件变化和观察／到达语义仍可能组织不当。
>
>【代码审阅解析】
> ①定位：[Extractor.classify][classify]的否定、假设、方向和移动正则；[Extractor.tourist][tourist]的`negative/confirmed`字典、相邻同名合并和回顾性出发地过滤；[Extractor.finalize][finalize]以步骤顺序编号。
>
> ②边界解析：官方主线与条件支线分离；游客叙述与列表分离；同日一旦记录某地点的未前往，列表阶段就优先排除该地点，没有按事件先后协调后续实际到访。`到了`正则也会命中“看到了”，把视线观察当成明确移动线索。邻接顺序为文本组织顺序，不是道路可达性证明。
>
> ③方案取舍：显式状态和证据比直接串联全部POI稳健；但按日／名称存布尔式否定，不能表示临时放弃后又到访等事件变化。建议建立事件级时间／顺序作用域，将看见、途经、停留、到达分开，并单独核验返回关系；不在本次修复。
>
>【核验证据】
>当前成功样例：云谷索道／太平索道是choose_one，光明顶支线返回天海，实际一线天列表节点因未前往被排除。
>本次诊断C3：“路线是：始信峰 -> 海心亭 -> 一线天 -> 光明顶。\n这次一线天人多未能前往。\n下午又到了一线天。”现有输出在叙述事件中保留一线天，却在报告列表排除同一地点，缺少事件级协调。
>真实文本C5：“看到了正在修正的北海宾馆”对应步骤状态为confirmed；这是规则候选，不证明实际入住或停留。核对[路线JSON][routes]、[核验清单][review]和原句。
>人工验收：将每个候选标为到达／途经／观察／未到访／计划，核对跨句和同日转折。报告应保留一线天双重证据、选择与返回关系、北海宾馆候选的人工判断；现有文件没有完成这些独立人工判定。

### 2.2.3 层级结构数据与结构图输出（12分）

>【评分条款原文】：3）输出层级结构数据和/或清晰的结构图（12分）。
>
>【完成情况结论】：【已完成】已有层级JSON、HTML和PNG/SVG，能够检查天数、时段、步骤以及部分特殊关系。
>
>【代码审阅解析】
> ①定位：[Extractor.finalize][finalize]构建`time_hierarchy`；[render_html][render]按天和时段展示并展开证据；[plot][plot_src]读取JSON绘制三列顺序图，末尾另写条件支线和排除提示。
>
> ②边界解析：HTML和JSON展示时段组，未知组不代表晚于其他组；静态图以步骤链和时间标签展示，不是完整地理地图。绘图的`lookup={route_kind:route}`仅保留每类最后一条，且图下注记写死黄山当前支线／一线天内容，不能宣称任意新增多路线输入都会完整制图。
>
> ③方案取舍：JSON提供可读取结构，HTML便于核对证据，静态图便于报告展示；绘图不承担地理规划，且目前只适配三种路线各1条的当前输入。建议如扩充语料，再按route_id分页并从实际数据生成注记；当前条款的“数据和／或结构图”已有直接产物支撑。
>
>【核验证据】
>已有产物：[路线JSON][routes]、[HTML][html]、[PNG][png]、[SVG][svg]。当前三类步骤数14／12／9与[摘要][summary]一致，条件支线在JSON／HTML独立保存，PNG以注记解释。
>人工验收：打开PNG检查中文、节点、箭头与图例，打开HTML展开任一原文；核对所有主线step_id恰好归属一个时段，支线锚点存在。报告应放置整体图及一段层级JSON，并注明箭头只是文本顺序。HTML尚无本次浏览器视觉验收证据，不应写成已做逐屏浏览器检查。

### 2.3 官方路线与游客实际路线对比（附加题额外加分，最多加至该实验上限100分；分数栏20分）

本组3个子条款均为附加加分项。原细目8＋12＋10＝30分，与分数栏20分不一致；以下不更改原始分值。

### 2.3.1 实际游览路线提取与可比表示（8分）

【⚠️本条为附加加分项】

>【评分条款原文】：1）从游客游记中提取或整理实际游览路线，并与官方路线进行可比对表示（8分）；
>
>【完成情况结论】：【部分完成】游客叙述与官方使用统一步骤结构，已处理明显未到访冲突；但当前输出仍是候选或报告路线，缺少独立核验的完整实际路线。
>
>【代码审阅解析】
> ①定位：[Extractor.tourist][tourist]构造`tourist_observed/tourist_declared`，保存`excluded_steps/corroborating_evidence`；[compare][compare]的`sequence`抽取规范名序列；[接入测试][tests_exp02]检查来源实体引用。
>
> ②边界解析：叙述12步包含无名交通和行程结束，不能直接视作12个实际景点。报告列表9步中西海饭店得到同日叙述支持，其余8步仅reported。没有自动从沉默叙述证实到访，也没有独立的路线级人工标注、完整时序真值或到访准确率。C3的先未去后到访仍不协调。
>
> ③方案取舍：分开保存叙述和列表，使不确定性可见，能在相同Schema下比较；但仍存在把观察线索提升为活动、叙述漏站和时间作用域不足的问题。建议由人工逐事件确认真实路线，保留未能确定的步骤，按事件级顺序处理转折，不以作者列表替代实际轨迹。本次不补标或修代码。
>
>【核验证据】
>真实成功证据：一线天在[路线JSON][routes]的列表排除项同时保存原列表和“未能前往”证据。当前游客叙述／报告路线及官方均保留来源和顺序。
>缺陷证据：C3中一线天同时出现在观察步骤和列表排除清单；C5的看见北海宾馆只支持观察候选，不能推出入住或停留。
>人工操作：验收人须逐段阅读HS_NOTE_001，整理“实际到访／经过／远观／未到访／计划／不确定”表，与[核验清单][review]和35条主线步骤逐条核对，才能支持“实际路线”验收。代码只提供中间件，没有完成人类确认。报告应展示该核对表、至少一个冲突案例及人工确认范围，不把AI规则结果改称人工金标。

### 2.3.2 至少两个维度的量化或结构对比（12分）

【⚠️本条为附加加分项】

>【评分条款原文】：2）至少从两个维度进行量化或结构对比，如景点覆盖度、顺序一致性、时间分配、路线相似度等（12分）；
>
>【完成情况结论】：【已完成】已计算地点覆盖维度和序列相似度维度，并导出公式、共同地点及差集；样本解释能力受重合度限制。
>
>【代码审阅解析】
> ①定位：[compare][compare]计算`official_poi_coverage/poi_jaccard/lcs_length/lcs_dice/shared_order_lcs_dice`；[lcs_length][lcs]实现动态规划；[run][run]生成两组比较及公式。
>
> ②边界解析：覆盖和Jaccard都属于地点集合比较，不能夸大为两个完全独立维度；另外的LCS确实使用保留重复访问的序列。排除transport、peripheral和无名活动，条件支线不并入官方主线。共同地点少于2个时，共同地点顺序一致性返回null。没有比较停留时长、真实路程或完整时间分配。
>
> ③方案取舍：集合指标便于识别覆盖差异，LCS提供文本顺序相似度，少共同点时返回空值避免虚假高一致性；代价是对命名粒度、分支选择和描述范围敏感。指标满足已实现的两类比较能力，但不是抽取准确率，也不是旅行方案优劣排名。
>
>【核验证据】
>已有[comparison.json][comparison]：官方与游客叙述的覆盖率、Jaccard、LCS Dice均为0；官方与游客报告路线分别约0.090909、0.055556、0.105263。后者共同地点仅海心亭，前者无共同主线地点，因此两组`shared_order_lcs_dice`均null。
>可复核推导：官方去交通后的地点集合11个，游客报告地点集合8个，交集1个；覆盖率1/11，并集18个故Jaccard=1/18，LCS为1而序列长度11＋8，故Dice=2/19。不要把0.105263写成10.53%的抽取准确率。
>人工验收：按实际导出的名称序列手算上述分母与交集，确认宾馆与父区域未强行合并；报告应放置指标表、公式、名称序列和null的原因。若教师要求有效顺序分析，应另核验更可比的路线，而不能把null当作已得到顺序一致性结论。

### 2.3.3 差异原因分析（10分）

【⚠️本条为附加加分项】

>【评分条款原文】：3）结合结果分析差异原因，而非仅给出数值/图片（10分）。
>
>【完成情况结论】：【已完成】既有报告已结合来源范围、天气／体力线索、叙述覆盖与名称粒度解释低重合，并明确非因果验证。
>
>【代码审阅解析】
> ①定位：[既有报告][report]“结果与对比”“验证及失败分析”部分；[compare][compare]输出`interpretation/official_only/tourist_only/shared_pois`，为解释提供结构证据；[数据说明][data_readme]给出来源范围。
>
> ②边界解析：官方是一日西海大峡谷路线，游客覆盖两天；部分节点只在列表出现；天海宾馆不等于天海，光明顶山庄不等于光明顶；光明顶属于官方可选支线而不进入必经主线比较。天气、体力是原文及报告支持的解释线索，不是受控实验已证明的独立原因。
>
> ③方案取舍：采用可回查的描述性解释，避免只贴数值或把低相似度等同于游客偏离；代价是样本只有一对文本，无法分离数据范围差异、抽取误差和游客行为差异各自的贡献。后续可用同范围标注及分支感知比较区分这些因素，现有代码没有此归因实验。
>
>【核验证据】
>证据链：[comparison.json][comparison]的差集与共同点→[路线JSON][routes]中的分支和来源→[报告][report]对雾、体力、两天范围和命名粒度的解释。游客游记中确有浓雾、膝盖体力及未前往一线天等内容，需以原文核对具体原因的适用对象。
>人工验收：每条解释至少对照一处原文或结构差异，剔除没有证据的推断；报告放置官方可选光明顶支线、游客两天层级、宾馆／片区名称对照和差集示例。此条无单独的人工金标要求，但教师仍应判断解释是否贴合实际文本。

### 2.4 名称归一化、噪声处理与稳健性（10分）

### 2.4.1 名称 噪声 重复与稳健性规则（10分）

>【评分条款原文】：对简称/全称、俗称/正式名、子景点/父区域、周边景点和重复实体等问题给出合理处理规则；避免明显过度对齐，并说明规则局限（10分）。
>
>【完成情况结论】：【部分完成】已保留实体粒度、过滤多类非到访信息并处理部分重复，但默认exp02模式没有通用简称／全称／俗称对齐，且已有解析与时序边界缺陷。
>
>【代码审阅解析】
> ①定位：[EntityIndex.mentions][mentions]的`re.sub(r'\s+','',text)`和子类型映射；[Extractor.mentions][mentions_mode]对exp02与dictionary分流；[本地词表][config]的`aliases`；[classify][classify]与[tourist][tourist]的外围、歧义、否定和相邻去重。
>
> ②边界解析：默认exp02使用上游原文名去空白，不应用本地aliases；不能把dictionary的云谷寺索道、猴子观海观景台等别名规则宣传为默认结果中的通用归一化。保留光明顶／山庄、天海／宾馆，town/resort归外围；相邻同日同名候选合并证据，返回及跨日不全局去重。云谷寺＋索道记歧义，小火车边界问题保留上游信息，不自动补齐。
>
> ③方案取舍：保守身份处理避免过度对齐，实例与canonical类别分离保护不同索道；代价是名称等价无法系统判定，低重合可能部分来自别名未对齐。C1/C2/C3/C4说明稳健性仍有限。建议建立可审核别名映射、父子包含关系和事件级去重，保留合并理由、来源及未决状态；不在本次增加规则。
>
>【核验证据】
>已有核验：[接入测试][tests_exp02]中不同索道同canonical仍保持不同来源ID；[路线JSON][routes]的光明顶山庄与光明顶、天海宾馆与天海分别存在；[核验清单][review]保留boundary_ambiguous／peripheral等状态。
>模式差异核对：检查[Extractor.mentions][mentions_mode]先走`entity_index.mentions`返回的分支，再查看[词表][config]，即可确认默认模式不会执行旧别名匹配。不能仅凭词表有aliases断定该评分点全部完成。
>人工验收：建立“原名—建议规范名—同一实体／父子关系／不同实体—来源—是否同意合并”的核对表，特别检查索道、酒店和区域；同时核对相邻重复与真实返回。本条的局限在[报告][report]已有说明，仍需人类确认合并政策。

### 2.5 报告与可复现性（10分）

### 2.5.1 规则 接口 指标与复现材料（10分）

>【评分条款原文】：报告说明解析规则、数据结构、指标计算方式、运行命令和输出文件，并给出代表性中间结果（10分）。
>
>【完成情况结论】：【已完成】已有README、Schema、实验报告、运行入口、公式、结构化中间件和测试，可复核核心输出；仍须按真实验证范围提交材料。
>
>【代码审阅解析】
> ①定位：[run及命令行参数][run]、[render_html][render]、[plot][plot_src]、[README][readme]、[SCHEMA][schema]、[既有实验报告][report]、[requirements-local.txt][requirements]及两份测试文件。
>
> ②边界解析：主入口只生成7个数据／HTML文件，PNG/SVG必须另跑绘图。主解析和测试只需标准库；绘图需matplotlib，项目2重跑另需jieba。默认模式不需要API密钥。测试使用临时目录，不能把测试产生的合成文本、上游删除对照或已有28项通过记录当作独立路线语义评估。
>
> ③方案取舍：源码、结构文件、说明和证据互相对应，有利于检查；当前无独立路线金标，HTML无浏览器视觉验收记录，绘图具有固定模板适用范围。建议提交时附带本次只读复现记录、明确失败案例和人工核验范围，而不是只给截图。
>
>【核验证据】
>本次只读重跑已有测试：28项全部通过，其中17项核心、11项接入；另用不写出结果的调用复现C1—C4，读取真实输出核对C5。这些新边界案例未加入测试集，也未修复代码。
>实验报告应包含：输入两条记录的编号与来源；官方选择／支线JSON；一线天列表与否定原文；21:00的TIME关联；云谷寺索道歧义；14／12／9步骤及未知时间统计；覆盖／LCS公式与结果；PNG整体图和至少一个展开原文样例；运行命令、依赖版本及失败清单。
>人工核验范围、核验人和结论由实际执行者补充，不应预填已人工验收。所有已有输出位置见1.3，复现命令见第3节；本文件本身为新增验收说明，不是替代原程序的实现成果。

## 3. 复现指引（从代码中提取）

### 3.1 依赖包列表

| 运行部分 | 直接依赖 | 说明 |
|---|---|---|
| 项目3默认解析 | Python标准库及本地模块entity_source | 读取已有实体，不需要jieba或模型 |
| 项目3测试 | 标准库unittest、tempfile等 | 会在临时目录创建并删除测试数据，不修改源码 |
| PNG/SVG绘图 | matplotlib | 代码设置Agg后端；优先加载Windows微软雅黑字体 |
| 可选重跑项目2 | jieba、matplotlib | 属于上游复现，不是本项目3默认入口必须执行的步骤 |

[requirements-local.txt][requirements]在Python 3.12上固定jieba==0.42.1、matplotlib==3.11.2。项目3标准库代码声明Python 3.10+；不能据此推断该固定第三方版本组合已在所有Python 3.10环境验证。需要安装时应针对已有虚拟环境执行安装命令，而不是改变系统Python。

### 3.2 工作目录与运行入口

仓库根目录：`D:\数据挖掘\DataMining-exp1`。已有本地虚拟环境可直接执行，无需激活：

```powershell
Set-Location -LiteralPath 'D:\数据挖掘\DataMining-exp1'
.\.venv\Scripts\python.exe experiments/exp03_route_hierarchy/src/route_hierarchy.py
.\.venv\Scripts\python.exe experiments/exp03_route_hierarchy/src/plot_hierarchy.py
.\.venv\Scripts\python.exe -m unittest discover -s experiments/exp03_route_hierarchy/tests -v
```

上述前两条会生成或覆盖默认输出。本次审阅没有执行这些默认导出命令。若验收人希望保留已有产物，可利用现有参数在独立目录重建，无须改代码：

```powershell
.\.venv\Scripts\python.exe experiments/exp03_route_hierarchy/src/route_hierarchy.py --output-dir D:/数据挖掘/.review/task3-reproduce
.\.venv\Scripts\python.exe experiments/exp03_route_hierarchy/src/plot_hierarchy.py --input D:/数据挖掘/.review/task3-reproduce/routes_huangshan.json --output-dir D:/数据挖掘/.review/task3-reproduce
```

本次仅运行测试时，在进程内将TEMP和TMP指向已有可写的 `D:\数据挖掘\.review`，并使用 `-B`避免写入字节码；没有修改系统环境设置。若验收环境临时目录正常可写，不需要此设置。

若需要重新安装第三方依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r experiments/exp03_route_hierarchy/requirements-local.txt
```

可选上游重建入口是 `experiments/exp02_entity_recognition/src/recognize_entities.py --version v2 --outputs <独立输出目录>`。重建结果应与项目3实际读取的实体文件核对；本次验收任务没有要求或执行修改项目2。

### 3.3 输入数据与全部输出位置

直接输入为：
1. `D:\数据挖掘\DataMining-exp1\data\processed\sample_v1.json`。
2. `D:\数据挖掘\DataMining-exp1\experiments\exp02_entity_recognition\outputs\entities_v2.json`。
3. `D:\数据挖掘\DataMining-exp1\experiments\exp03_route_hierarchy\config\huangshan_pois.json`。

默认输出根目录为 `D:\数据挖掘\DataMining-exp1\experiments\exp03_route_hierarchy\outputs`，完整产物如下：

| 文件名 | 生成入口 | 核查重点 |
|---|---|---|
| routes_huangshan.json | route_hierarchy.py | Schema、来源实体、三类路线、支线、时间和证据 |
| route_steps.csv | route_hierarchy.py | 35条主线记录、原文偏移、来源ID；不是全部支线展开 |
| hierarchy.html | route_hierarchy.py | 天数／时段组和可展开原文 |
| comparison.json | route_hierarchy.py | 两组比较、公式、共同点和差集 |
| review_cases.json | route_hierarchy.py | 待人工复核，不能当成人工已判定 |
| integration_report.json | route_hierarchy.py | 上游哈希与位置检查，不是语义准确率 |
| summary.json | route_hierarchy.py | 14／12／9步骤、1条支线、1个排除节点 |
| hierarchy.png | plot_hierarchy.py | 当前三类路线各1条，中文及箭头可辨识 |
| hierarchy.svg | plot_hierarchy.py | 同图的矢量版本 |

已有说明材料为[README][readme]、[SCHEMA][schema]、[实验报告][report]；本次新增文件是当前《Task3 游览路线的层级结构挖掘 考核项自检验收文档》，不由项目3程序自动生成。表格仅列实际代码定义的文件，没有补造人工金标、人工评分表、准确率评估文件或新的数据集。

### 3.4 关键配置参数及作用

| 入口 | 参数 | 默认值或实际行为 |
|---|---|---|
| route_hierarchy.py | --input | 仓库data/processed/sample_v1.json |
| route_hierarchy.py | --entities | 项目2outputs/entities_v2.json；默认exp02模式严格校验 |
| route_hierarchy.py | --scenic-id | huangshan；必须与配置scenic_id相符 |
| route_hierarchy.py | --config | 本项目config/huangshan_pois.json |
| route_hierarchy.py | --entity-mode | exp02；dictionary仅为独立词表基线，两种模式不能混报 |
| route_hierarchy.py | --output-dir | 本项目outputs；显式相对路径相对当前工作目录 |
| plot_hierarchy.py | --input | 本项目outputs/routes_huangshan.json |
| plot_hierarchy.py | --output-dir | 本项目outputs；只生成hierarchy.png与hierarchy.svg |

重要实现参数还包括：`ARROW`支持的连接符、编号行正则、非嵌套括号正则、`PERIODS`、时钟时段阈值、POI／具名交通过滤、按日／名称保存的否定字典。它们都来自源码，不是外部模型参数。缺失当前景区任一文档的实体、非法位置、未知文档、重复／重叠实体会报错；不存在“上游错误后自动退回词表”的默认行为。

## 4. Review总结：现存问题与扣分预判

### 4.1 逐条结论汇总

| 条款 | 原分值 | 结论 | 验收重点 |
|---|---:|---|---|
| 2.1.1 描述模式分析 | 10 | 已完成 | 区分实际黄山格式与合成编号例 |
| 2.1.2 统一结构表示 | 15 | 已完成 | 字段、来源和未知值明确，不把存在字段当作已填语义 |
| 2.1.3 程序与导出 | 15 | 部分完成 | C1混合编号漏项、C2嵌套支线错误 |
| 2.2.1 时间层级 | 15 | 部分完成 | 大量未知、C4凌晨区间、有限行程日支持 |
| 2.2.2 组织合理性 | 13 | 部分完成 | C3事件变化、C5观察与到达混淆 |
| 2.2.3 层级数据／图 | 12 | 已完成 | 当前结果可核查；多路线绘图和固定注记有限制 |
| 2.3.1 实际路线整理 | 8，附加 | 部分完成 | 规则／报告候选未独立人工确认完整实际轨迹 |
| 2.3.2 至少两个维度 | 12，附加 | 已完成 | 地点集合＋序列指标；共同地点顺序为null |
| 2.3.3 差异原因分析 | 10，附加 | 已完成 | 描述性解释有证据，不等于已证明因果 |
| 2.4.1 归一化与稳健性 | 10 | 部分完成 | 默认没有通用别名归并，噪声与时序处理有边界 |
| 2.5.1 报告及复现 | 10 | 已完成 | 依赖、入口、文件及中间证据齐全，验证范围需准确 |

共覆盖**11条带分值的细目**：6条已完成、5条部分完成、0条整体未完成，其中3条为附加加分项。没有整条未完成不表示所有子能力均存在；例如通用别名对齐、完整实际轨迹人工确认、跨句时间推断、停留时长估计仍没有实现或证据。它们在对应“部分完成”条款中列明，没有新增任务书之外的独立扣分条款。

### 4.2 已复现边界案例及失效机制

本次C1—C4为明确标记的合成诊断，未加入正式数据或测试文件。C1—C3直接调用已有Extractor核心函数，使用现有dictionary模式隔离路线控制逻辑；不是默认exp02全链路新增语料验收。C4直接调用已有period函数。C5来自真实默认输出。

| 编号 | 可复现输入或现有片段 | 实际行为 | 应核验的业务语义与机制 |
|---|---|---|---|
| C1 | “1. 上午游览始信峰”换行“下午游览光明顶” | 只输出始信峰 | 命中任一编号即只处理编号行，导致未编号续段漏抽 |
| C2 | 天海（如体力允许（例如晴天），先上光明顶，再返回天海）→海心亭 | 主线含光明顶与返回天海，条件支线数0 | 非嵌套括号正则丢失外层条件作用域 |
| C3 | 列表含一线天；后文先说人多未前往，再说下午又到了一线天 | 叙述有一线天，报告列表仍将其排除 | negative按天和名称存储，缺少同日事件先后和计划更新 |
| C4 | TIME.clock为0030 | 返回morning | hour<11把凌晨并入上午；真实样本21:00不受此例影响 |
| C5 | 看到了正在修正的北海宾馆 | confirmed，规则为explicit_movement | “到了”子串命中“看到了”；不能据此证明到访、停留或入住 |

另外存在从代码可直接推导的边界，尚未逐项跑完整输入：多个同类route_kind在静态绘图lookup中覆盖，只显示最后一条；绘图支线与一线天注记写死；未命中别名但实际同一地点时默认仍按不同原文名处理；时段只支持局部关联，未知组不证明真实时间空白；“第三天”等不属于day_at现有显式映射。必须将这些与“已复现实例”分开，不夸大验证覆盖。

### 4.3 可能被扣分的位置与人工评分边界

- **解析可靠性（2.1.3，15分）**：正常文件能导出，不能因此掩盖C1/C2。建议教师在混合格式和嵌套条件下检查漏抽、主线／支线混淆，再决定该条实际给分。
- **时间层级（2.2.1，15分）**：数据结构已完成，但32/35主线步骤时间未知，且有凌晨规则缺陷。未知信息应保持未知；不能为了减少扣分补造官方时段。是否接受unknown及相对天数，应结合来源和教师对“等价时间层级”的口径。
- **先后及活动组织（2.2.2，13分）**：C3未协调、C5待判定，属于当前规则的业务边界。不能把状态confirmed解释成人类已经确认真实到访。
- **实际路线附加项（2.3.1，8分）**：现有列表多数节点仅reported，没有人工整理的完整真实路线。只提交图或比较分数，可能不足以支撑该细目满分。
- **归一化与稳健性（2.4.1，10分）**：默认模式没有通用别名对齐，本地配置文件的aliases不能作为默认能力证据；还需检查父子关系、周边与真实返回。
- **展示与报告的额外风险**：若只运行主入口而漏运行绘图，提交目录不会新生成PNG/SVG；若把固定图注当作动态解析输出、把2.3.2的LCS Dice写成准确率，或省略人工核验范围，会削弱对应证据。当前已有文件存在，并不代表任意新输入都能完整出图。

以上为扣分风险定位，不是自动扣分或自评总分。单景区黄山是当前明确开发范围，项目3步骤也允许选取1—2个景区；不能把项目1或项目2的其他独立评分条款挪来重复扣分。附加20分／细目30分的矛盾必须先由教师确认，不在本文件中私自换算。

### 4.4 对应修改建议 仅描述方案

1. **C1与格式覆盖**：统一编号模式判定与分段条件；将未编号文本保留在结构中，再决定其为续段、标题或新步骤；用真实混合格式核验漏抽。
2. **C2与条件作用域**：使用括号栈或区间树建立嵌套关系；条件、远观和主线分别按作用域解析，锚点从条件前的实际步骤确定。
3. **C3与实际路线**：由按日／名称的否定字典升级为事件级状态序列，保存先未去、后到访等变化；明确报告列表、计划与实际轨迹之间的关系。
4. **C4与时间**：定义夜间、凌晨与上午的边界；扩充相对日表达；跨句时间只能在有依据时关联，并保留来源及不确定性。时长不得自动转换为景点停留时长。
5. **C5与候选活动**：区分观察、远观、途经、到达、停留与入住；人工检查北海宾馆等真实样例，建立独立路线核验表后再评价语义质量。
6. **名称与实体粒度**：维护有依据的别名／简称映射及父子包含关系；保留实体原名和合并理由；不同索道实例不能因canonical相同而合并。
7. **多路线展示**：静态图按route_id分页或分组，图注由当前数据计算；保留JSON／HTML中的完整范围，避免lookup覆盖。
8. **验收证据**：提交一对原文与结构化步骤、条件支线、未到访冲突、时间依据、指标手算和人工判定记录；将正常回归测试与新发现的失效案例分别记录。

这些均为后续可选改动方案，**本次没有实施，没有提供修改后的实验源码，也没有补写人工验收结论**。

[route_src]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L1
[entity_src]: ../experiments/exp03_route_hierarchy/src/entity_source.py#L1
[plot_src]: ../experiments/exp03_route_hierarchy/src/plot_hierarchy.py#L10
[config]: ../experiments/exp03_route_hierarchy/config/huangshan_pois.json
[tests_core]: ../experiments/exp03_route_hierarchy/tests/test_route_hierarchy.py
[tests_exp02]: ../experiments/exp03_route_hierarchy/tests/test_exp02_integration.py
[readme]: ../experiments/exp03_route_hierarchy/README.md
[schema]: ../experiments/exp03_route_hierarchy/SCHEMA.md
[report]: ../reports/exp03_huangshan.md
[requirements]: ../experiments/exp03_route_hierarchy/requirements-local.txt
[data_readme]: ../data/README.md
[input]: ../data/processed/sample_v1.json
[entities]: ../experiments/exp02_entity_recognition/outputs/entities_v2.json
[routes]: ../experiments/exp03_route_hierarchy/outputs/routes_huangshan.json
[csv]: ../experiments/exp03_route_hierarchy/outputs/route_steps.csv
[html]: ../experiments/exp03_route_hierarchy/outputs/hierarchy.html
[png]: ../experiments/exp03_route_hierarchy/outputs/hierarchy.png
[svg]: ../experiments/exp03_route_hierarchy/outputs/hierarchy.svg
[comparison]: ../experiments/exp03_route_hierarchy/outputs/comparison.json
[review]: ../experiments/exp03_route_hierarchy/outputs/review_cases.json
[integration]: ../experiments/exp03_route_hierarchy/outputs/integration_report.json
[summary]: ../experiments/exp03_route_hierarchy/outputs/summary.json
[official]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L123
[split]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L35
[parens]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L56
[step]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L85
[tourist]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L219
[finalize]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L282
[classify]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L186
[mentions]: ../experiments/exp03_route_hierarchy/src/entity_source.py#L68
[mentions_mode]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L72
[day]: ../experiments/exp03_route_hierarchy/src/entity_source.py#L84
[period]: ../experiments/exp03_route_hierarchy/src/entity_source.py#L97
[time_step]: ../experiments/exp03_route_hierarchy/src/entity_source.py#L117
[run]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L389
[render]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L350
[compare]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L311
[lcs]: ../experiments/exp03_route_hierarchy/src/route_hierarchy.py#L300
[number_test]: ../experiments/exp03_route_hierarchy/tests/test_route_hierarchy.py#L76

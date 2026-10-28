# Task2 游览步骤的实体识别 考核项自检验收文档

> 审阅对象：`experiments/exp02_entity_recognition/` 下全部现有代码与产物
> 审阅原则：只读审阅，未修改、补全、重构任何代码，未新增功能

## 1. 任务基础信息

**实验目标**（摘抄任务书）：识别程序性文本中的核心要素（景点POI、交通方式、时间节点）。

**审阅信息**：本次审阅基于用户提供的、已开发完成的仓库代码，代码来源为
`experiments/exp02_entity_recognition/`（`src/recognize_entities.py`、`src/evaluate.py`、
`src/config/lexicon.json`、`src/config/stopwords.json`、`README.md`）及其已有产物
（`outputs/` 下 12 个文件）。审阅过程中未改动任何源码、配置与产物。

**技术栈**（从 `import` 与配置中提取）：

| 类别 | 内容 |
|---|---|
| 语言/运行时 | Python 3.10+（实际运行于 3.12） |
| 第三方库 | `jieba`（分词与自定义词典）、`matplotlib`（柱状图，含 `font_manager`、`MaxNLocator`） |
| 标准库 | `argparse`、`csv`、`json`、`re`、`sys`、`unicodedata`、`collections`、`pathlib` |
| 模型 | 无。未调用任何 LLM 或预训练模型 |
| 数据集 | 教师/仓库提供的开发样本 `data/processed/sample_v1.json`，本轮仅使用 `scenic_id=huangshan` 的 2 条（`HS_OFF_001` 官方路线 136 字、`HS_NOTE_001` 游记 2711 字）；未自行采集 |

**全部产出文件清单**：

| 路径 | 类型 | 产生方式 |
|---|---|---|
| `outputs/entities_v1.json` | JSON 数组，97 条 | `--version v1` |
| `outputs/entities_v2.json` | JSON 数组，100 条 | `--version v2` |
| `outputs/stats_v1.json` / `stats_v2.json` | JSON 统计 | 同上 |
| `outputs/entity_freq_v1.csv` / `_v2.csv` | CSV（entity_type, text, canonical, count） | 同上 |
| `outputs/entity_freq_v1.png` / `_v2.png` | 三联柱状图 | 同上 |
| `outputs/gold_huangshan.json` | 人工金标 55 项 | 手工整理（AI 初标） |
| `outputs/evaluation.json` | 两版 P/R/F1 与误漏清单 | `evaluate.py` |
| `outputs/entity_spec.md` | 实体定义规范表 | 手工撰写 |
| `outputs/manual_check.md` | 逐条人工抽查记录 | 手工撰写 |
| `outputs/iteration_log.md` | v1→v2 迭代记录 | 手工撰写 |
| `README.md` | 依赖、运行、输入输出说明 | 手工撰写 |

## 2. 评分细则逐条审阅校验

> 说明：任务书实验项目 2 的评分表**不含附加加分项**（五项考核项合计 100 分），故本文档无 `【⚠️本条为附加加分项】` 标记。

### 2.1 考核项一：实体类型定义与规范（15 分）

#### 2.1.1 三类实体的定义、边界和示例（10 分）

>【评分条款原文】：1）明确景点POI、交通方式、时间节点三类实体的定义、边界和示例（10分）；

>【完成情况结论】：**已完成** —— 三类实体的定义、判定依据、正反例与边界规则均有显式文档承载，并与机读词表一一对应。

>【代码审阅解析】
> ①定位：
> - 定义与子系统：`outputs/entity_spec.md` 第 2 节，分 2.1（POI，15 个子类型）、2.2（交通方式，5 个子类型）、2.3（时间节点，5 个子类型）三张表，每行给出「子类型—说明—示例」。
> - 边界规则：同文件第 3 节共 11 条（最长匹配优先、交通设施不单独成实体、索道线路名归交通方式、方位区域计入而方位通名不计、住宿餐饮按节点计入、无名称通名不标、数字时刻需上下文校验、路线产品名不计、景区外地点不计、不为凑数补写、`canonical` 不可作实体 ID）；第 3.1 节补充粒度分层表。
> - 机读定义：`src/config/lexicon.json` 的 `poi`（31 条）/`transport`（13 条）/`time`（11 条），每条含 `subtype` 与 `note`；`excluded` 段记录 7 类不纳入词及理由（`一日游`、`秋冬季节`、`此次`、`下次`、`观景台`、`山顶`、`酒店`）。
> - 代码侧常量：`TYPE_ORDER`（POI=0/TRANSPORT=1/TIME=2）、`TYPE_CN`、`GROUP_OF`；判定顺序写在 `detect_v2()` 内。
> ②边界解析：
> - 判定存在明确优先级：时间闭类词 → 交通词表 → POI 词表 → 数字时刻（含上下文否定）→ 后缀兜底；重叠时 `resolve_overlaps()` 按「长实体优先、同跨度 POI>TRANSPORT>TIME」取舍。
> - 显式排除三类易误判对象：无名称通名（`山顶`/`观景台`/`平台`/`景区`/`宾馆`）、跨出景区的地点（`上海`）、路线产品名（`一日游`）。
> - 同形歧义有固定处置：`索道` 一律计交通方式、不重复计 POI；`云谷索道` 与 `云谷寺` 分属两类；`光明顶` 与 `光明顶山庄` 靠最长匹配分离。
> ③方案取舍：
> - 客观事实：类型定义放在文档 + 词表双处，而非写在代码注释或枚举类中。
> - 优点：定义与实现解耦，换景区只需替换词表；规范表可直接复用为报告素材，满足「形成实体定义规范表」的要求。
> - 缺点：双份维护存在漂移风险——例如 `excluded` 中 `秋冬季节`、`此次`、`下次` 只是文档约束，代码里并没有对应判定逻辑；`V1_TIME_WORDS` 仍保留 `一日`，与 `excluded` 中「`一日游` 不计时间」的表述需要结合分词结果才能自洽。

>【核验证据】
> - 输入：`data/processed/sample_v1.json` 中 `scenic_id == huangshan` 的 2 条记录。
> - 预期输出：`outputs/entities_v2.json` 共 100 条，三类齐全，`stats_v2.json.by_type` = `{POI: 65, TRANSPORT: 23, TIME: 12}`。
> - 产物路径：`outputs/entity_spec.md`、`outputs/entities_v2.json`、`outputs/stats_v2.json`。
> - 人工操作：按 `entity_spec.md` 第 2 节的子类型清单，逐一核对 JSON 中 `subtype` 取值是否都有定义；用 `stats_v2.json.by_type` 核对三类计数与文档一致。此条为文档与数据一致性检查，不需要额外标注。

#### 2.1.2 多景区定义一致性与易混淆说明（5 分）

>【评分条款原文】：2）定义在多个景区之间保持一致，并说明容易混淆的情况（5分）。

>【完成情况结论】：**部分完成** —— 易混淆说明充分（第 4 节 12 行对照表），但「多个景区之间保持一致」未实现：词表、后缀、停用词全部按黄山定制，换景区会大面积失效。

>【代码审阅解析】
> ①定位：
> - `src/recognize_entities.py` 的 `load_records(path, scenic_id)` 与 `main()` 的 `--scenic` 参数（默认 `huangshan`）；`extract()` 对单景区记录循环。
> - `src/config/lexicon.json` 顶层 `"scenic_scope": "huangshan"`，无多景区分表。
> - `src/evaluate.py` 只读取单一金标 `gold_huangshan.json`，无跨景区评估分支。
> - 全仓库无任何「跨景区一致性校验」代码或产物。
> ②边界解析：
> - 同一景区内多篇文本可正常处理（当前 2 篇），实体类型与子类型在文档内自洽。
> - 跨景区时仅「能跑」而非「能用」：实测 `--scenic gugong` 得到 10 条 mention / 6 个唯一名，其中仅 `午门`、`御花园`、`神武门`（出现 2 次）基本正确，`门楼`、`香亭` 属通名误判，`角楼` 是 `西北角楼` 的不完整切分；`--scenic xihu` 仅 5 条，唯一 POI 为 `风景区`（误判）。
> - 原因可定位到后缀表：`V2_POI_SUFFIX` 为「峰/寺/亭/楼/宾馆/景区/顶/海/台/谷/门/园/山庄/饭店/度假区」，不覆盖故宫的「殿/宫/馆」与西湖的「荷区/堤/桥」。
> ③方案取舍：
> - 客观事实：选择了「单景区高精度词表」而非「跨景区通用规则」。
> - 优点：在黄山语料上精确率/覆盖率均达 0.98，结果确定、可解释、零成本复现。
> - 缺点：迁移性差；任务书「对比多个景区的识别结果，归纳出适用于景区领域的实体类型体系」的方法要求实际未落地，属方法论层面的缺口，不只是分数问题。

>【核验证据】
> - 可复现输入：`python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2 --scenic gugong --outputs <临时目录>`，预期 `mentions=10`、`unique_names.POI=6`；`--scenic xihu` 预期 `mentions=5`、`unique_names.POI=1`。
> - 产物路径：现有 `outputs/entity_spec.md` 仅描述黄山；`outputs/` 下无任何故宫/西湖的实体文件。
> - 补该评分点所需改动（仅方案）：把词表拆为 `config/common.json`（跨景区通用类别词）+ `config/lexicon.<scenic>.json`，`load_lexicon(scenic)` 按景区加载，`extract()` 汇总三景区分布并输出一致性检查表；`scenic_scope` 字段改为按文件声明。

### 2.2 考核项二：实体识别方法实现（35 分）

#### 2.2.1 三类实体识别方法（15 分）

>【评分条款原文】：1）采用Jieba+自定义词典、规则方法或LLM方法之一完成三类实体识别（15分）；

>【完成情况结论】：**已完成** —— 采用 jieba 分词 + 自定义词典 + 规则，三类实体均稳定产出。

>【代码审阅解析】
> ①定位：
> - 词典注入：`register_lexicon(lexicon)`，对 `poi`/`transport`/`time` 三组词调用 `jieba.add_word(word, freq=20000)`，仅在 `--version v2` 时执行。
> - 带偏移分词：`tokenize(text)` 使用 `jieba.tokenize()` 返回 `(word, start, end)`，并用 `is_noise_token()` 过滤空白、标点、符号、emoji（Unicode 类别 P/Z/S/C）。
> - 规则判定：`detect_v1()`（纯后缀/闭类词/数字）与 `detect_v2()`（词表优先 + 闭类词 + 数字上下文 + 后缀兜底）。
> - 组装与去冲突：`extract()` 逐文档收集候选并调用 `resolve_overlaps()`；`decorate()` 补 `granularity`/`canonical`。
> ②边界解析：
> - 三条识别路径并存：词表命中（`method=lexicon`）、闭类词（`keyword`）、数字/正则（`number`、`regex_day`）、后缀兜底（`suffix`）。
> - 位置约束由断言 `assert text[start:end] == text` 保证，且使用 Python Unicode 字符索引，与 `docs/data_contract.md` 一致。
> - 在黄山语料上，v2 的全部 POI 均来自词表（`method=lexicon`），后缀兜底路径未被触发；该路径仅在故宫/西湖试跑时生效。
> ③方案取舍：
> - 客观事实：选择离线词典+规则，而非 LLM 抽取。
> - 优点：无网络与密钥依赖、结果确定可复现、每位实体的命中路径可追溯（`method` 字段）。
> - 缺点：不具备语义泛化能力，未见过的专名只能靠后缀猜边界，且猜出的结果需要人工复核（`granularity=unknown`）。

>【核验证据】
> - 命令：`python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2`
> - 预期输出：`mentions=100`、`by_type={POI:65, TRANSPORT:23, TIME:12}`
> - 产物：`outputs/entities_v2.json`、`outputs/stats_v2.json`
> - 人工操作：无（该条为程序能力判定）

#### 2.2.2 词典/规则设计合理性与覆盖度（10 分）

>【评分条款原文】：2）词典/规则/Prompt设计合理，能覆盖景区专属词与常见表达（10分）；

>【完成情况结论】：**部分完成** —— 黄山专属词覆盖较好（31 个 POI、4 条具名索道线路），但存在明确缺口：`小火车` 未覆盖导致边界错误，且「常见表达」仅限本语料实际出现过的说法。

>【代码审阅解析】
> ①定位：
> - 词表：`src/config/lexicon.json`，POI 31 条（含 `西海大峡谷北入口`、`猴子观海`、`光明顶山庄`、`东黄山旅游度假区` 等长词）、交通 13 条（含 4 条具名索道/缆车线路）、时间 11 条。
> - 停用词：`src/config/stopwords.json` 的 `suffix_noise`（26 条）抑制通名、`generic_place`（12 条）拦截被切开的景区名前缀、`off_scenic`（1 条 `上海`）、`time_number_reject_context`（10 个量词）。
> - 规则：`V2_POI_SUFFIX`（15 个后缀，含 `山庄/饭店/度假区`）、`V2_NUMBER` 四位数字 + 后 8 字上下文否定、`V2_T_PLUS` 匹配 `T + 1`。
> ②边界解析：
> - 已覆盖的专属表达：`西海大峡谷北入口` 走最长匹配，未被拆成 `西海`+`大峡谷`；`猴子观海` 整体成词，不再抛 `观海`；`云谷索道/太平索道/玉屏索道/西海观光缆车` 与泛称 `索道` 分列。
> - 未覆盖的表达：`小火车` 不在词表，jieba 切为 `小`+`火车`，`火车` 命中词表，产出错误实体（`evaluation.json` 中 TRANSPORT `false_positive=[火车]`、`false_negative=[小火车]`）。
> - 停用词为精确 token 匹配：`西海` 被整体拦截，因此在黄山语料中抑制碎片是有效的，但若新语料出现独立片区名「西海」，会被静默丢弃，属于过拟合。
> - 「索道站/索道上站/索道下站」按规范不计为独立实体，可能被评审视为漏识别，需在报告中说明是有意设计。
> ③方案取舍：
> - 客观事实：用人工穷举词表 + 通用后缀兜底，而不是统计学习或 LLM 生成候选。
> - 优点：可解释、可审计、每处改动都能在 `iteration_log.md` 中对上；停用词按类型分层，便于定位误杀。
> - 缺点：覆盖面完全依赖人工枚举，长尾专名（小火车、观光车、地轨等）容易漏；停用词与当前语料强耦合。

>【核验证据】
> - 金标 55 项，v2 命中 54 项，唯一漏项为 `小火车`；见 `outputs/evaluation.json` 的 `by_type.TRANSPORT`。
> - 可复现样例：原文「从山上可以看到西海大峡谷小火车轨道」→ v2 输出 `西海大峡谷`(POI) + `火车`(TRANSPORT)；预期应为 `西海大峡谷`(POI) + `小火车`(TRANSPORT)。
> - 产物：`src/config/lexicon.json`、`src/config/stopwords.json`、`outputs/evaluation.json`。
> - 人工操作：打开 `lexicon.json` 核对 31+13+11 条是否覆盖报告所举的景区专属词；对 `manual_check.md` 中列出的漏项（`小火车`）确认是否接受为已知缺陷。

#### 2.2.3 批量处理多个景区文本（6 分）

>【评分条款原文】：3）批量处理多个景区文本，代码可运行且结果稳定（6分）；

>【完成情况结论】：**部分完成** —— 支持同一景区内多篇文本的批量循环，但**不支持一次处理多个景区**；且统计中的 `scenic_id` 被写死为 `huangshan`，换景区时标签错误。

>【代码审阅解析】
> ①定位：
> - `main()` 通过 `--scenic` 单值过滤：`records = load_records(args.input, args.scenic)`，一次只处理一个景区。
> - `summarize()` 返回字典中 `'scenic_id': 'huangshan'` 为**字面量常量**，未使用入参。
> - 输出文件名 `entities_{version}.json`、`stats_{version}.json` 不含景区标识，同一 `--outputs` 目录下不同景区会互相覆盖。
> ②边界解析：
> - 同景区多篇：`extract()` 内 `for record in records` 正确累加，`per_doc` 按 `doc_id` 分组，当前 2 篇均处理。
> - 换景区：必须手动改 `--scenic` 并另指 `--outputs`，否则上一景区结果被覆盖；即使另指目录，`stats` 中 `scenic_id` 仍为 `huangshan`，元数据错误。
> - 无跨景区汇总逻辑，无多次运行的回归对比机制。
> ③方案取舍：
> - 客观事实：脚本按「单景区一次运行」设计，而非「多景区批处理」。
> - 优点：实现简单，单次运行结果可直接人工核对。
> - 缺点：不满足「批量处理多个景区文本」的字面要求；连续运行存在结果覆盖与标签错位风险。

>【核验证据】
> - 可复现缺陷：先 `--scenic gugong --outputs X`，再 `--scenic xihu --outputs X`，第二次运行会覆盖第一次的 `entities_v2.json`；查 `stats_v2.json` 的 `scenic_id` 仍为 `huangshan`。
> - 产物：`outputs/stats_v2.json`（观察 `scenic_id` 字段）。
> - 人工操作：需在报告中若声称「已处理多景区」，必须补充逐景区独立目录的证据，否则该条按未覆盖计。
> - 补该评分点所需改动（仅方案）：`summarize()` 增加 `scenic_id` 入参；输出路径带景区前缀（如 `entities_{scenic}_{version}.json`）；新增 `--scenic all` 或批处理脚本，循环三个景区并汇总 `stats`。

#### 2.2.4 保留类型、来源与出现位置（4 分）

>【评分条款原文】：4）保留实体类型、来源及出现位置等必要信息（4分）。

>【完成情况结论】：**已完成** —— 实体记录含类型、来源标识（`doc_id`/`scenic_id`）、精确位置、句号与命中方式；来源链接通过 `doc_id` 间接回溯，未直接落在实体记录中。

>【代码审阅解析】
> ①定位：
> - 记录构造：`extract()` 中每个候选字典包含 `doc_id`、`scenic_id`、`text`、`entity_type`、`subtype`、`start`、`end`、`sentence_id`、`method`；`decorate()` 追加 `granularity`、`canonical`。
> - 句子归属：`split_sentences()` 按 `。！？；!?;\n` 切句并保留绝对偏移，`sentence_of()` 用区间判定归属。
> - 位置校验：`extract()` 末尾断言 `text[start:end] == text`。
> ②边界解析：
> - 位置口径为 Python Unicode 字符索引、左闭右开，与 `docs/data_contract.md` 的强制要求一致，不使用字节偏移或 UTF-16 长度。
> - 同一名称多次出现会生成多条独立记录（mention 级），位置各不相同；名称级去重只在 `evaluate.py` 中发生，不影响实体文件。
> - 来源为 `doc_id`（如 `HS_OFF_001`），可据此在 `data/metadata/sources.json` 查到 `source_url`、`publisher`、`license`；实体文件本身不含 URL。
> ③方案取舍：
> - 客观事实：采用 `doc_id` 外键式引用，不冗余存 URL 与发布时间。
> - 优点：字段精简、避免同一来源信息在每条实体上重复；与仓库既有数据契约一致。
> - 缺点：单独拿到 `entities_v2.json` 无法直接看到出处，评审若要求「来源」可见，需要额外查表或补 `source_url` 字段。

>【核验证据】
> - 取 `entities_v2.json` 任一记录，用 `data/processed/sample_v1.json` 中同 `doc_id` 的 `clean_text` 做切片，应严格相等。
> - 预期：100 条记录全部满足 `clean_text[start:end] == text`；按 `(doc_id, start, end)` 无重复。
> - 产物：`outputs/entities_v2.json`、`data/metadata/sources.json`。
> - 人工操作：抽查 3 条实体的 `doc_id` 在 `sources.json` 中是否可查到对应来源与许可。

### 2.3 考核项三：识别结果与质量检查（20 分）

#### 2.3.1 结构化实体文件（8 分）

>【评分条款原文】：1）输出结构化实体文件（如JSON），格式正确、字段清晰（8分）；

>【完成情况结论】：**已完成** —— 输出标准 JSON 数组，字段固定、UTF-8 无 BOM、LF 换行，位置可校验。

>【代码审阅解析】
> ①定位：
> - 写出逻辑：`main()` 中 `json.dumps(entities, ensure_ascii=False, indent=2)` + `write_text(..., encoding='utf-8', newline='\n')`；统计文件 `stats_{version}.json` 同法写出。
> - 结构：顶层为数组，元素为扁平对象，无嵌套。`stats` 含 `by_type`、`unique_names`、`by_canonical`、`granularity`、`per_doc`。
> ②边界解析：
> - 每次运行覆盖同名文件，不做增量合并；`v1` 与 `v2` 通过文件名共存。
> - 仅靠代码内 `assert` 保证位置正确，**没有 JSON Schema 校验或独立校验脚本**。
> - `subtype` 在两版中语义不同：v1 为占位值（`suffix`/`mode`），v2 为语义子类型（`peak`/`lodging`/`cableway` 等），混用两版数据会出错。
> ③方案取舍：
> - 客观事实：直接输出数组而非带 `meta` 的信封结构。
> - 优点：下游一行 `json.load` 即可读取，无需解析包装层。
> - 缺点：缺少 `version`、`generated_at`、`scenic` 等文件级元信息（仅靠文件名与 `stats` 携带），不利于长期归档。

>【核验证据】
> - 预期：`entities_v2.json` 为长度 100 的数组；每条含 11 个字段。
> - 产物：`outputs/entities_v1.json`、`entities_v2.json`、`stats_v1.json`、`stats_v2.json`。
> - 人工操作：用任意 JSON 校验器打开，确认无语法错误；抽查 3 条确认字段齐全。

#### 2.3.2 人工抽查与改进（8 分）

>【评分条款原文】：2）人工抽查若干样例，分析误识别、漏识别或歧义实体，并给出基本改进（8分）；

>【完成情况结论】：**部分完成** —— 抽查记录本身详实（v1 全量 97 条 + v2 全量 100 条，含 8 个典型错例、10 条正例、边界判定说明），但**抽查由 AI 初查、未经组员签字确认**；v2 唯一残留错误 `小火车` 未在迭代中修复。

>【代码审阅解析】
> ①定位：
> - `outputs/manual_check.md`：1.1 错误分类表、1.2 典型错例 8 条（含原文片段与 v1 输出对照）、1.3 漏识清单、2.1 v2 残留错误、2.2 正确性抽查 10 条、2.3 边界判定 4 条、三、已知局限 4 条。
> - 量化支撑：`outputs/gold_huangshan.json`（55 项名称级金标）与 `src/evaluate.py::prf()`（TP/FP/FN、P/R/F1）。
> - 改进记录：`outputs/iteration_log.md` 第 2 节的词典/停用词/规则三项改动。
> ②边界解析：
> - 评估粒度为名称级：`norm()` 仅去空白，以 `(doc_id, entity_type, text)` 为集合元素，**不评位置级正确性、不罚部分匹配**（例如 `光明顶` 出现在 `光明顶山庄` 内部不会被判错）。
> - 金标与词表同源：`gold_huangshan.json` 与 `lexicon.json` 由同一轮阅读整理，导致 v2 的 0.98 属上限值，不能当泛化准确率；此点已在 `iteration_log.md` 第 4 节主动披露。
> - 样本仅 2 篇、55 个金标名，无训练/测试划分，无法宣称统计显著性。
> ③方案取舍：
> - 客观事实：用名称级集合评估替代 span 级对齐评估。
> - 优点：在 55 个名字规模上可操作、可复算，能明确列出误识与漏识清单。
> - 缺点：无法发现「边界切错但名字对」的问题（`小火车` 被识为 `火车` 恰属此类，靠人眼而非指标发现）。

>【核验证据】
> - 代码产出的中间文件：`gold_huangshan.json`（金标）、`evaluation.json`（P/R/F1 与误漏清单）、`entities_v1.json` 与 `entities_v2.json`（待抽查对象）。
> - 人类必须执行的操作：① 按 `manual_check.md` 的抽查表抽取 ≥20 条，对照 `data/processed/sample_v1.json` 的 `clean_text` 逐条核对边界与类型；② 对 `gold_huangshan.json` 的 55 项金标复核，重点确认 `谷底`、`徽味楼`、`前山/后山` 是否应计入 POI；③ 在文档上签字确认，否则该条只能按「未经人工确认」计。
> - 预期结果：v2 精确率/覆盖率 0.98、残留 1 处边界错误（`小火车`）。

#### 2.3.3 无大规模噪声、重复或类型混乱（4 分）

>【评分条款原文】：3）结果无明显大规模噪声、重复或类型混乱（4分）。

>【完成情况结论】：**已完成** —— 无重叠、无重复记录、无跨文档串位；仅存在 1 处边界错误与 1 处粒度争议（已在文档中标注）。

>【代码审阅解析】
> ①定位：
> - 去重叠：`resolve_overlaps()` 按「长优先、类型优先」贪心保留互不重叠的候选。
> - 去重来源：`tokenize()` 返回的 `(word, start, end)` 位置天然唯一，`extract()` 未做二次去重，但也不会产生同位置重复；`T + 1` 分支在追加前检查与现有候选是否重叠。
> - 类型混乱控制：`V1_TRANSPORT_WORDS`/`lexicon.transport` 与 POI 词表无交集，`索道` 只在交通组出现。
> ②边界解析：
> - 相邻但不重叠的实体允许并存（如 `西海大峡谷` 与 `北入口` 已由最长匹配合并为 `西海大峡谷北入口`）。
> - 类型争议点：`徽味楼`（餐馆）计入 POI/lodging 之外的 `restaurant` 子类型；`谷底`（通名）计入 POI，理由是在官方路线中明确为换乘节点；`火车` 由 `小火车` 切出，属边界错误而非类型错误。
> - 无独立校验脚本，当前结论依赖 `resolve_overlaps()` 的结构性保证 + 一次性手工核验。
> ③方案取舍：
> - 客观事实：用「最长匹配 + 类型优先级」的确定性规则替代打分式冲突消解。
> - 优点：结果可预测，同一输入必得同一输出，便于复现。
> - 缺点：没有自动化测试守护，后续改词典可能悄悄引入重叠；该结论目前只有一次性验证，无持续保障。

>【核验证据】
> - 预期：`entities_v2.json` 100 条，按 `(doc_id, start, end, entity_type)` 无重复；同一文档内实体区间两两不重叠。
> - 产物：`outputs/entities_v2.json`、`outputs/stats_v2.json`（`by_type` 三类计数之和应等于 `entity_mentions`）。
> - 人工操作：可用 3 行脚本对 JSON 做上述两项断言；当前仓库未内置该检查。

### 2.4 考核项四：词频可视化与迭代优化（20 分）

#### 2.4.1 三类实体词频统计与可视化（10 分）

>【评分条款原文】：1）统计三类实体词频并生成词云或柱状图等可视化（10分）；

>【完成情况结论】：**已完成** —— 生成分类型词频 CSV 与三联横向柱状图（条款为「词云或柱状图」，柱状图已满足）。

>【代码审阅解析】
> ①定位：
> - 统计：`write_frequency()` 以 `Counter((entity_type, text, canonical))` 计数，按「类型→canonical→次数降序→名称」排序写出 CSV。
> - 绘图：`plot_frequency()` 生成 3 行 1 列子图，每类取 Top10 横向 `barh`，标注数值；`MaxNLocator(integer=True)` 保证刻度为整数；通过 `font_manager.addfont` 加载 `C:\Windows\Fonts\msyh.ttc` 解决中文显示。
> - 图注：`fig.text` 声明「按原文表面形式统计、未按 canonical 合并」，并指引到 `stats_{version}.json` 的 `by_canonical`。
> ②边界解析：
> - Top10 截断：超出部分不出现在图中，但完整计数保留在 CSV。
> - 具名与泛称不合并：`索道`（泛称 10 次）与 `云谷索道`（2 次）、`玉屏索道`（2 次）、`太平索道`（1 次）、`西海观光缆车`（1 次）分列，避免「看不出走了哪条索道」。
> - 未做词云：不引入 `wordcloud` 依赖，也无中文遮罩处理。
> ③方案取舍：
> - 客观事实：选柱状图而非词云。
> - 优点：柱状图能表达次数差异且可精确读数，适合实体种类少（31/10/7 个唯一名）的场景；无额外依赖。
> - 缺点：视觉吸引力弱于词云；Top10 截断会丢失长尾信息（已在 CSV 保留）。

>【核验证据】
> - 命令：`--version v2` 运行后自动产出。
> - 产物：`outputs/entity_freq_v2.csv`（列：`entity_type,text,canonical,count`）、`outputs/entity_freq_v2.png`（三子图，标题含「按原文表面形式」）。
> - 预期读数：POI 榜首 `光明顶`8；交通榜首 `索道`10（泛称），其后 `云谷索道`2/`玉屏索道`2；时间榜首 `日落`4。
> - 人工操作：无，打开图片即可核对。

#### 2.4.2 基于可视化的迭代与前后对比（10 分）

>【评分条款原文】：2）根据可视化结果调整停用词、领域词典或规则，并说明优化前后变化（10分）；

>【完成情况结论】：**已完成** —— v1 词频图暴露「碎片+通名霸榜」后，做了词典/停用词/规则三类改动，并用同一金标与两版图对比，变化有量化记录。

>【代码审阅解析】
> ①定位：
> - 版本开关：`main()` 的 `--version {v1,v2}` 决定是否执行 `register_lexicon()`、是否走 `detect_v2()`、是否启用数字上下文与 `T+1` 正则。
> - 三项改动落在：`register_lexicon()`（词典）、`stopwords.json`（停用词与上下文词）、`detect_v2()` 中 `V2_NUMBER` + `reject_ctx` + `V2_T_PLUS` + `V2_POI_SUFFIX`（规则）。
> - 变化说明：`outputs/iteration_log.md` 第 1～3 节（触发信号、改动表、指标表），第 6 节（粒度追加）。
> ②边界解析：
> - 迭代依据来自可视化：v1 图中 POI 前三为 `西海`10/`光明顶`9/`宾馆`5，交通 `索道`15，时间出现 `1000`/`1100`；这些读数直接对应三项改动。
> - 两版共用同一金标与同一评估脚本，比较基准一致。
> - 迭代只改 v2 分支，v1 逻辑完整保留，可随时复现对照。
> ③方案取舍：
> - 客观事实：保留双版本产物而非只留最终版。
> - 优点：形成「基线—改动—指标」的完整证据链，符合评分细则对「说明优化前后变化」的要求。
> - 缺点：产物数量翻倍（4 个 JSON/CSV + 2 张图），报告需额外解释两版差异；v1 的 `subtype` 为占位值，与 v2 语义不一致。

>【核验证据】
> - 指标对比（同一金标）：v1 总体 P 0.43 / R 0.36；v2 总体 P 0.98 / R 0.98。分类型见 `outputs/evaluation.json`。
> - 图对比：`outputs/entity_freq_v1.png`（`西海`10、`宾馆`5、`索道`15、`1100`）对 `entity_freq_v2.png`（`光明顶`8、`西海饭店`6、具名索道各 2、`T + 1`）。
> - 产物：`outputs/iteration_log.md`、两版 CSV/PNG/JSON。
> - 人工操作：报告中需并排放两张图并标注三处改动对应的现象，否则「前后变化」不易被判为已说明。

### 2.5 考核项五：报告与可复现性（10 分）

>【评分条款原文】：说明方法选择、主要参数/词典或 Prompt、运行方式、输入输出及代表性结果；关键步骤可被复现（10分）。

>【完成情况结论】：**部分完成** —— 方法选择、词典参数、运行方式、输入输出、代表性结果均在 README 与三份 md 中有说明，三条命令可完整复现；但**没有正式实验报告正文**，且缺 `requirements.txt` 与自动化测试。

>【代码审阅解析】
> ①定位：
> - `README.md`：状态与范围、输入、依赖、运行（3 条命令 + 4 个可选参数）、输出清单、方法要点 5 条、结果摘要、目录结构、已知限制。
> - 方法细节：`outputs/entity_spec.md`（定义与边界）、`outputs/iteration_log.md`（改动与指标）、`outputs/manual_check.md`（抽查与错例）。
> - 复现入口：`src/recognize_entities.py::main()` 与 `src/evaluate.py::main()`，路径通过 `Path(__file__).resolve().parents[3]` 定位仓库根，不依赖当前工作目录。
> ②边界解析：
> - 路径健壮性：脚本可从任意目录调用（已在仓库外目录验证可运行），输入默认 `data/processed/sample_v1.json`，可用 `--input` 覆盖。
> - 环境依赖风险：字体路径硬编码 `C:\Windows\Fonts\msyh.ttc`，非 Windows 或未装微软雅黑时回退到 `SimHei`/`DejaVu Sans`，可能导致中文方块；未提供 `requirements.txt`，`jieba` 与 `matplotlib` 版本未锁定。
> - 无单元测试、无 CI，`assert` 在 `python -O` 下会被跳过。
> ③方案取舍：
> - 客观事实：用 Markdown 分文件承载材料，尚未合并成报告。
> - 优点：分工写作友好，每份材料对应一个评分维度，便于评审按图索骥。
> - 缺点：缺少统一叙事与图表编号，评审若只看 README 可能低估工作量；报告未成文直接对应 10 分项打折。

>【核验证据】
> - 复现命令：`python experiments/exp02_entity_recognition/src/recognize_entities.py --version v1|v2`、`python experiments/exp02_entity_recognition/src/evaluate.py`。
> - 预期产物：`outputs/` 下 12 个文件全部重新生成，`evaluation.json` 复算得 v1 0.43/0.36、v2 0.98/0.98。
> - 报告应放置的佐证材料：① `entity_freq_v1.png` 与 `entity_freq_v2.png` 并排图；② `entities_v2.json` 片段（3～5 条，展示 `text` 与 `start/end` 对应）；③ `evaluation.json` 的 P/R/F1 表；④ 8 个典型错例的原文截图或表格；⑤ 词典与停用词条目数统计；⑥ 三条命令的执行日志截图。
> - 人工操作：把上述材料合并为正式报告（建议结构：任务与方法 → 数据与词典 → 结果与评估 → 迭代过程 → 失败案例与局限），并补齐 `requirements.txt` 与运行截图。

## 3. 复现指引（从代码中提取）

**1）依赖包列表**（由 `import` 提取）

- 标准库：`argparse`、`csv`、`json`、`re`、`sys`、`unicodedata`、`collections`（`Counter`、`defaultdict`）、`pathlib`
- 第三方：`jieba`、`matplotlib`（`pyplot`、`font_manager`、`ticker.MaxNLocator`）
- 无模型、无网络、无密钥

**2）运行入口与命令**（仓库根目录执行）

```bash
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v1
python experiments/exp02_entity_recognition/src/recognize_entities.py --version v2
python experiments/exp02_entity_recognition/src/evaluate.py
```

**3）输入数据路径**

- 默认：`data/processed/sample_v1.json`（按 `scenic_id == huangshan` 过滤，使用 `clean_text`）
- 来源元数据：`data/metadata/sources.json`（按 `doc_id` 回溯 URL 与许可）

**4）全部输出产物路径**

`experiments/exp02_entity_recognition/outputs/` 下：
`entities_v1.json`、`entities_v2.json`、`stats_v1.json`、`stats_v2.json`、
`entity_freq_v1.csv`、`entity_freq_v2.csv`、`entity_freq_v1.png`、`entity_freq_v2.png`、
`gold_huangshan.json`、`evaluation.json`、`entity_spec.md`、`manual_check.md`、`iteration_log.md`。

**5）关键配置参数**

| 参数/常量 | 取值 | 作用 |
|---|---|---|
| `--version` | `v1` / `v2` | 选择基线或优化版流程 |
| `--scenic` | 默认 `huangshan` | 景区过滤，单值 |
| `--input` / `--outputs` | 默认仓库数据与实验目录 | 输入输出路径 |
| `jieba.add_word(freq=)` | `20000` | 提高自定义词优先级，防切碎 |
| `V2_NUMBER` + `reject_ctx` 窗口 | 4 位数字，后 8 字符 | 判定四位数字是否为时刻 |
| `V2_POI_SUFFIX` | 15 个后缀 | 未登录 POI 的后缀兜底 |
| `plot_frequency` TopN | 10 | 每类图中展示条数 |
| `MAX` 字体 | `C:\Windows\Fonts\msyh.ttc` | 中文渲染 |

## 4. Review 总结：现存问题与扣分预判

### 4.1 部分完成/未完成的评分细目

| 编号 | 考核细目 | 分值 | 结论 | 建议给分 |
|---|---|---|---:|---:|
| 2.1.1 | 三类实体定义、边界、示例 | 10 | 已完成 | 10 |
| 2.1.2 | 多景区一致 + 易混淆说明 | 5 | 部分完成 | 2.5 |
| 2.2.1 | 三类实体识别方法 | 15 | 已完成 | 15 |
| 2.2.2 | 词典/规则覆盖度 | 10 | 部分完成 | 8 |
| 2.2.3 | 批量处理多个景区文本 | 6 | 部分完成 | 2 |
| 2.2.4 | 保留类型/来源/位置 | 4 | 已完成 | 4 |
| 2.3.1 | 结构化实体文件 | 8 | 已完成 | 8 |
| 2.3.2 | 人工抽查与改进 | 8 | 部分完成 | 6 |
| 2.3.3 | 无噪声/重复/类型混乱 | 4 | 已完成 | 4 |
| 2.4.1 | 词频统计与可视化 | 10 | 已完成 | 10 |
| 2.4.2 | 基于可视化的迭代与对比 | 10 | 已完成 | 10 |
| 2.5 | 报告与可复现性 | 10 | 部分完成 | 7 |
| **合计** | | **100** | | **86.5** |

> 附加加分项：无。

### 4.2 代码会失效的边界案例

1. **换景区即失效**：`--scenic gugong` 仅得 10 条 mention（6 个唯一名，其中 3 个为通名误判）；`--scenic xihu` 仅 5 条，唯一 POI 为误判的 `风景区`。
2. **`scenic_id` 标签写死**：`summarize()` 中为字面量 `huangshan`，任何 `--scenic` 非黄山的运行都会产出错误元数据。
3. **多景区输出互相覆盖**：`entities_{version}.json` 不含景区名，连续运行不同 `--scenic` 到同一 `--outputs` 会覆盖。
4. **`小火车` 边界错误**：被切为 `小`+`火车`，产出 `火车`（FP）并漏掉 `小火车`（FN），是全量评估里唯一的错误。
5. **停用词误杀风险**：`generic_place` 中的 `西海`/`北海`/`莲花`/`鳌鱼` 为精确 token 拦截，若新语料出现独立片区名会被静默丢弃。
6. **设施不计数**：`索道站`、`索道上站`、`索道下站` 按规范不计，可能被判为漏识别（属设计选择，需报告说明）。
7. **字体缺失环境**：`plot_frequency()` 依赖 `msyh.ttc`，缺失时回退字体可能导致中文方块。
8. **`assert` 可被优化掉**：`python -O` 下位置校验失效。
9. **两版 `subtype` 语义不一致**：v1 为 `suffix`/`mode` 占位值，v2 为语义值，混用会出错。

### 4.3 预判扣分点

| 扣分点 | 影响条款 | 预估扣分 |
|---|---|---:|
| 只用黄山一个景区，未做多景区一致性 | 2.1.2、2.2.3 | 约 6.5 |
| 词典未覆盖 `小火车`，遗留唯一错误 | 2.2.2 | 约 2 |
| 人工抽查未签字、残留错误未改进 | 2.3.2 | 约 2 |
| 无正式实验报告正文 | 2.5 | 约 3 |
| 缺 `requirements.txt`、无测试 | 2.5 | 含在上项内 |

### 4.4 修改建议（仅方案，不提供代码）

1. **多景区支持**（对应 2.1.2 / 2.2.3）：
   - 词表拆为 `common.json`（跨景区类别词：索道/缆车/大巴/时段词）+ `lexicon.<scenic>.json`；
   - `load_lexicon(scenic)` 按景区加载，`summarize()` 增加 `scenic_id` 入参；
   - 输出文件名带景区前缀；新增批处理入口一次跑三景区并输出跨景区类型分布对比表。
2. **补齐领域词**（对应 2.2.2）：
   - 词表加 `小火车`，并在匹配阶段加「左侧为修饰语时抑制短词」的负向规则，避免 `火车` 在 `小火车` 中命中；
   - 对 `索道站` 类设施明确二选一：或新增 `FACILITY` 类型，或维持不计数并在报告中显式声明。
3. **降低停用词过拟合**（对应 2.2.2）：
   - 把 `generic_place` 的裸词拦截改为「上下文条件拦截」（如仅当左侧紧邻 `大峡谷/饭店/观光` 时才丢弃）。
4. **人工确认闭环**（对应 2.3.2）：
   - 组员对 `manual_check.md` 抽检 ≥20 条并签字；对 `gold_huangshan.json` 55 项复核；
   - 决定 `小火车` 是修复还是作为已知失败案例保留（若保留，需在报告中说明设计取舍）。
5. **可复现性加固**（对应 2.5）：
   - 增加 `requirements.txt` 锁定 `jieba`、`matplotlib` 版本；
   - 字体改为候选列表探测（`msyh.ttc` → `simhei.ttf` → 内置字体），并在日志中打印实际使用字体；
   - 增加最小测试（位置校验、三类计数、去重断言），避免依赖 `assert`。
6. **报告成文**（对应 2.5）：
   - 按 4.2 所列材料合并为正式报告；把 `iteration_log.md` 的指标表与两张图并排呈现，明确「0.98 为上限值、非泛化准确率」的口径说明。

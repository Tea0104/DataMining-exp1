# 黄山游览路线层级结构挖掘

项目3的黄山开发版本，默认读取项目2的 `entities_v2.json`，仅处理共享语料中的黄山官方路线 `HS_OFF_001` 和游客游记 `HS_NOTE_001`。输出官方主线、条件支线、游客叙述事件、报告路线及时间层级，并计算描述性结构对比。

代码基于项目2分支 `feat/exp02-entity-recognition` 的提交 `4a16120643181f1615e85476604aa7aceafb1796`。项目2代码及验收文档分别经PR #1、#2进入主分支。项目3与验收文档经负责人授权，沿用原有 `feat/exp02-entity-recognition` 分支提交PR；推送前已同步该分支的后续文档提交。

## 运行

项目3解析器和测试只用Python 3.10+标准库，读取项目2已经提交的实体文件即可运行：

```powershell
python experiments/exp03_route_hierarchy/src/route_hierarchy.py
python -m unittest discover -s experiments/exp03_route_hierarchy/tests -v
```

本机已在仓库根目录部署 `.venv`，实际版本为Python 3.12。无需激活环境：

```powershell
.\.venv\Scripts\python.exe experiments/exp03_route_hierarchy/src/route_hierarchy.py
.\.venv\Scripts\python.exe -m unittest discover -s experiments/exp03_route_hierarchy/tests -v
.\.venv\Scripts\python.exe experiments/exp03_route_hierarchy/src/plot_hierarchy.py
```

绘图和项目2重跑使用jieba、matplotlib，可在Python 3.12虚拟环境中通过本模块的 `requirements-local.txt` 安装本次验证版本。虚拟环境不提交Git。

参数：`--input` 指定共享JSON，`--entities` 指定项目2实体JSON，`--output-dir` 指定输出目录，`--scenic-id` 默认huangshan。默认路径相对脚本定位；显式相对路径相对当前工作目录解析。

默认 `--entity-mode exp02` 严格使用上游mention，不用本地词表回填缺失实体。文件缺失、位置错配、类型错误、重复或重叠会报错。保留 `--entity-mode dictionary` 作为原独立开发基线，必须输出到另一个目录；默认交付结果不是该模式。

## 方法和衔接

1. 读取项目2的全部100个实体，校验编号、景区、类型和Python字符位置。实体保留原文名、子类型、粒度与稳定来源编号；`canonical` 只用于类别，不作节点身份。
2. 路线候选使用POI及具名交通实体，泛称交通作为活动上下文关联，TIME实体用于相对日和局部时间关联。没有把所有提及直接当成已到访。
3. 官方按括号外箭头或编号列表解析，保存二选一交通、条件支线、返回锚点和远观提及。编号格式当前由合成输入验证；真实黄山文本是箭头与叙述混合格式。
4. 游客叙述按移动线索、否定、假设、他人行程和回顾性引用区分状态。箭头列表单独保存，同日明确未前往节点移入排除清单。
5. 时间组织为相对天数→时段→步骤。只将同一局部分句中的上游TIME赋给活动；行程时长不当作景点停留时长。其余TIME保留在文档时间上下文中。
6. 当前来源的“云谷寺索道”在项目2中拆为云谷寺与泛称索道，输出待核验歧义和线路未消解的上山活动，不自动合并为云谷索道。第二天21:00对应行程结束，不虚构景点。

`confirmed` 表示规则找到了明确叙述线索，尚未经过独立人工评估；`reported` 仅在作者列表报告；`corroborated` 表示列表与同日叙述有共同证据。候选事件不保证构成完整实际轨迹，顺序也不证明直接道路连通。

## 结果与文件

当前生成官方14个主线步骤、1条可选往返支线；游客叙述12个活动步骤；游客列表排除一线天后保留9个步骤。官方全部时段仍未知。测试共28项通过，不等于抽取准确率。

| 文件 | 用途 |
|---|---|
| `outputs/routes_huangshan.json` | 完整步骤、支线、来源实体引用、时间层级和原文证据，项目6优先读取 |
| `outputs/route_steps.csv` | 主线步骤平表，UTF-8 BOM，包含上游实体引用 |
| `outputs/hierarchy.html` | 可展开证据的层级页面 |
| `outputs/hierarchy.png` / `hierarchy.svg` | 静态图，可用于报告，使用绘图脚本生成 |
| `outputs/comparison.json` | 覆盖、Jaccard与LCS指标、公式和边界 |
| `outputs/review_cases.json` | 分支、歧义、非主线提及、否定冲突的核验清单 |
| `outputs/integration_report.json` | 项目2实体哈希、数量、位置检查及已知上游问题 |
| `outputs/summary.json` | 本次输入和输出数量、校验状态 |

字段见 [Schema说明](SCHEMA.md)，实验方法、验证结果、局限及评分对照见 [项目3报告](../../reports/exp03_huangshan.md)。

## 本地检查与提交边界

项目3沿用项目2原有分支协作，交付包含本模块、实验报告和逐条验收文档；本地虚拟环境、缓存及旧草稿备份不属于仓库交付。

优先检查层级图、HTML原文证据、实验报告和[考核项自检验收文档](../../reports/Task3_游览路线的层级结构挖掘_考核项自检验收文档.md)，再核对JSON。本次提交保留已审阅实现；验收中列出的混合编号、嵌套支线、同日事件协调和凌晨时段等边界问题尚未修复。

两条开发文本缺少完整时间安排与独立路线金标准，当前结果不支持跨景区泛化或最终准确率声明。项目2金标也声明为AI初标待人工复核，不能直接当成项目3路线金标准。

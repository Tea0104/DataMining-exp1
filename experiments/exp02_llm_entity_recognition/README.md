# 实验二 · 另一种方法：LLM 景点抽取

本目录是实验二的独立对照。LLM 读取游览原文，返回景点 POI 的原文名称。程序核对名称确实出现在所处理的片段，再计算原文字符位置，保留逐篇的模型返回名称及被拒绝的名称。

固定语料上同时报告独立抽取与规则补漏。独立抽取只用正文和景区名。补漏读取 v3 或 v7 产物，在原有三类实体之外加入不重叠的模型景点。另对 v7 的新增候选做一次上下文复核，只接受模型在候选清单中确认的名称。合并产物保存在本目录，已有实体的边界保留。

## 当前方案与结果

独立方法用 DeepSeek V4.1 Flash 分别按原提示和严格提示抽取候选。两版一致的名称直接保留，分歧候选由全文复核确认，最后在本地修正名称边界和路线节点。独立方法使用正文和景区名，v7 作为评分对照。此分支聚焦 POI，评估以同篇、同类型、同原文名称为单位。

| 数据 | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|
| 原 25 篇，独立 LLM 方法 | 91.51% | 92.94% | 92.22% |
| 原 25 篇，v7 对照 | 95.89% | 91.57% | 93.68% |
| 黄山两篇，沿用投票并修正后处理 | 97.06% | 91.67% | 94.29% |

黄山修正前的迁移初测为 85.29% F1，修正后属于开发复测。黄山参考含 36 个 POI，由助手初标。 [原 25 篇结果](outputs/deepseek_v41_flash_1017_route_boundary_remaining25/evaluation.json) · [黄山初测](outputs/huangshan_transfer/evaluation.json) · [黄山复测](outputs/huangshan_route_scope/evaluation.json)

可从已保存的投票产物离线复算原 25 篇的最终结果。在仓库根目录执行：

```powershell
$llmDir = 'experiments/exp02_llm_entity_recognition'
python -B "$llmDir/refine_boundaries.py" "$llmDir/outputs/deepseek_v41_flash_1017_review_vote_remaining25" --output "$llmDir/outputs/reproduced_route_boundary"
```

## 复现

本地试验使用 llama.cpp b11887 Vulkan 后端。Python 客户端仅使用标准库。 [llama.cpp 运行器](https://github.com/ggml-org/llama.cpp/releases/tag/b11887) · [Qwen2.5 官方权重](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)

在仓库根目录启动本地服务。默认模型为 Qwen3-4B-Instruct-2507，使用 Unsloth 的 Q5_K_M 权重。 [模型说明](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) · [GGUF 权重](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF)

```powershell
& .cache/exp02_llm/runtime-vulkan/llama-server.exe -m experiments/exp02_llm_entity_recognition/.cache/qwen3-4b-instruct-2507-q5_k_m.gguf -c 4096 -t 8 -ngl 99 --parallel 1 --host 127.0.0.1 --port 8089 --alias qwen3-4b-2507
```

另开终端运行抽取：

```powershell
& .venv/Scripts/python.exe -B experiments/exp02_llm_entity_recognition/run.py --model qwen3-4b-2507 --output experiments/exp02_llm_entity_recognition/outputs/qwen3_4b_context_verified_remaining25
```

默认处理原实验二固定的 25 篇对照语料。可用 `--pilot` 只取每个景区首篇官方路线和首篇游记，另设输出目录。同一输出目录按逐篇产物续跑，模型、提示词、脚本或评估输入变化时需使用新目录。默认每段正文最多 550 字，另提供前后各最多 110 字参考，输出名称在本段正文内定位。llama.cpp 本机接口用 JSON 结构约束生成。

复跑 1.5B 对照时，把权重路径改为 `.cache/exp02_llm/qwen2.5-1.5b-instruct-q4_k_m.gguf`，服务别名和客户端 `--model` 都改为 `qwen25-15b`，输出目录改为 `outputs/qwen25_15b_context_verified_remaining25`（相对于本目录）。

用 `--input` 指定自定义 JSON 文件可抽取新景区。输入为记录数组，每条包含 `doc_id`、`scenic_id`、`scenic_name`、`clean_text`，搭配 `--pilot` 时还需要 `text_type`。自定义输入只生成独立抽取产物。

远端模型可使用兼容 Chat Completions 且支持 JSON 对象响应的 HTTPS 服务。用环境变量 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 配置。接口会接收待抽取的原文片段与提示词。 [服务接口说明](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

DeepSeek V4.1 Flash 使用 `--base-url https://api.deepseek.com --model deepseek-flash`。脚本为该接口关闭思考模式，并在提示末尾补上接口要求的 `json` 格式标记。使用 `--chunk-size 260` 与本地 4B 短窗口对照。将 Key 通过进程环境变量 `LLM_API_KEY` 传入，使用新输出目录。 [模型版本](https://api-docs.deepseek.com/updates/) · [JSON 输出要求](https://api-docs.deepseek.com/guides/json_mode/)

## 输入与输出

- 原文读取 `data/processed/full/selected_v2/dataset.json`。参考标注只在本地用于评分，读取 `experiments/exp02_entity_recognition/outputs/gold_remaining25.json`。v3 和 v7 对照从同目录读取已有实体产物。
- `manifest.json` 保存运行配置与输入哈希。`documents/<doc_id>.json` 保存模型候选、原文位置和复核记录。独立结果在 `llm_entities.json`，v3 补漏在 `hybrid_entities.json`，v7 的直接补漏及复核后补漏分别在 `v7_hybrid_entities.json` 和 `v7_verified_entities.json`。`evaluation.json` 保存 POI 的精确率、召回率、F1 和逐项差异。
- 名称级比较按 `doc_id + 实体类型 + 去空白的原文名称` 去重。25篇的参考由助手标注，已用于旧方法开发。成绩反映这次本地模型在固定语料上的表现，陌生景区泛化需另设人工评估。

## 旧版六篇试跑

使用 CPU 后端，每个景区取固定参考中的首篇官方路线和首篇游记。共165个景点参考项、14次模型请求。 [六篇结果](outputs/qwen25_15b_pilot/evaluation.json)

| 方法 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| v3 | 130 | 5 | 35 | 96.30% | 78.79% | 86.67% |
| 本地 LLM | 62 | 21 | 103 | 74.70% | 37.58% | 50.00% |
| v3 + LLM | 139 | 21 | 26 | 86.88% | 84.24% | 85.54% |

合并后补回了「关帝祠」「山西会馆」「宋摩崖」等9项，也新增了「泰山门票」等16个未匹配参考的名称。原文校验可以排除正文不存在的字符串，判断正文片段是否属于 POI 仍需要语义证据。

## 旧版固定 25 篇对照

完整对照使用同一份 Qwen2.5 权重及 Vulkan 后端，处理25篇、510个景点参考项。47次模型请求均完成，逐段原文校验拒绝了25个模型返回名称。复核确认 v3 的对照得分与既有评价一致，混合实体的原文位置有效，且全部保留该范围内的 v3 实体。 [完整结果](outputs/qwen25_15b_remaining25/evaluation.json) · [运行环境](outputs/qwen25_15b_remaining25/runtime.json)

| 方法 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| v3 | 378 | 19 | 132 | 95.21% | 74.12% | 83.35% |
| 本地 LLM | 192 | 53 | 318 | 78.37% | 37.65% | 50.86% |
| v3 + LLM | 397 | 54 | 113 | 88.03% | 77.84% | 82.62% |

模型补漏多找回19项，包括「北普陀寺」「山西会馆」「关帝祠」，同时新增35项未匹配参考的预测。例子包括把「东北明珠」和「东奉弥勒佛」当作景点。合并后景点召回率提高3.72个百分点，F1下降0.73个百分点。当前本地小模型更适合作为待筛选的候选来源。表中成绩对应所记录的 Vulkan 运行，六篇 CPU 试跑单独保存。

## 改进版固定 25 篇对照

新提示覆盖路线链、简称、碑刻和命名景物，分段保留邻近上下文。1.5B 复核实验从上次保存的逐篇结果续跑。 [1.5B 分段](outputs/qwen25_15b_context_remaining25/evaluation.json) · [1.5B 复核](outputs/qwen25_15b_context_verified_remaining25/evaluation.json) · [4B 默认窗口](outputs/qwen3_4b_context_verified_remaining25/evaluation.json) · [4B 短窗口](outputs/qwen3_4b_short_context_remaining25/evaluation.json) · [双模型一致补漏](outputs/v7_llm_consensus_remaining25/evaluation.json)

| 方法 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| v7 | 467 | 20 | 43 | 95.89% | 91.57% | 93.68% |
| 1.5B 独立抽取（复核试验中的候选） | 212 | 97 | 298 | 68.61% | 41.57% | 51.77% |
| v7 + 1.5B 直接补漏 | 470 | 71 | 40 | 86.88% | 92.16% | 89.44% |
| v7 + 1.5B 复核补漏 | 470 | 47 | 40 | 90.91% | 92.16% | 91.53% |
| 4B 独立抽取，550 字窗口 | 358 | 113 | 152 | 76.01% | 70.20% | 72.99% |
| 4B 独立抽取，260 字窗口 | 384 | 140 | 126 | 73.28% | 75.29% | 74.27% |
| v7 + 4B 直接补漏，550 字窗口 | 474 | 79 | 36 | 85.71% | 92.94% | 89.18% |
| v7 + 4B 复核补漏，550 字窗口 | 474 | 51 | 36 | 90.29% | 92.94% | 91.59% |
| v7 + 4B 复核补漏，260 字窗口 | 480 | 73 | 30 | 86.80% | 94.12% | 90.31% |
| v7 + 双模型一致补漏，550 字窗口 | 469 | 25 | 41 | 94.94% | 91.96% | 93.43% |

4B 短窗口的独立 F1 较旧版 1.5B 提升 23.41 个百分点，距 v7 还有 19.41 个百分点。默认窗口的复核补回「宋摩崖」「汉柏第一」「孔子小天下处」等 7 项，另有 31 项未匹配参考，包含普通设施名、景区本体和描述性短语。双模型一致补漏只收下 1.5B 与 4B 均复核确认的同篇同名候选，补回「白猿墓」「西门」，新增 5 个未匹配项。它使用 v7 作底座，F1 仍低 0.25 个百分点。

短窗口试验在抽取命令上加 `--chunk-size 260`，输出目录用 `outputs/qwen3_4b_short_context_remaining25`。双模型一致补漏可用已完成的两个默认窗口输出复算：

```powershell
$llmDir = 'experiments/exp02_llm_entity_recognition'
& .venv/Scripts/python.exe -B "$llmDir/compare_consensus.py" "$llmDir/outputs/qwen25_15b_context_verified_remaining25" "$llmDir/outputs/qwen3_4b_context_verified_remaining25" --output "$llmDir/outputs/v7_llm_consensus_remaining25"
```

## DeepSeek V4.1 Flash 对照

用官方 `deepseek-flash`（V4.1 Flash-1017，关闭思考模式）跑同一批 25 篇，使用相同的 260 字窗口及抽取规则，另加 API 要求的 JSON 格式标记。共记录 146 次分段抽取和 73 次补漏复核。 [逐项评测](outputs/deepseek_v41_flash_1017_short_context_remaining25/evaluation.json)

| 方法 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-4B 独立抽取 | 384 | 140 | 126 | 73.28% | 75.29% | 74.27% |
| DeepSeek V4.1 Flash 独立抽取 | 469 | 164 | 41 | 74.09% | 91.96% | 82.06% |
| v7 | 467 | 20 | 43 | 95.89% | 91.57% | 93.68% |
| v7 + DeepSeek 复核补漏 | 488 | 78 | 22 | 86.22% | 95.69% | 90.71% |

DeepSeek 独立 F1 比本地 4B 高 7.79 个百分点，召回率略高于 v7，精确率差距仍大。「主入口」「停车场」「芦苇荡」等普通设施和景观描述仍会被报作景点。

## DeepSeek 提示词对照

`prompt_precision.txt` 要求逐项检查候选是否有可识别的名称、是否属于目标景区的游览范围。使用虚构地名举例，区分路线里的普通设施与明确的景区出入口、完整名称与独立出现的别名、题刻与普通引语。复核提示词、模型和 260 字窗口与前一轮一致。

已在 Windows 用户环境变量保存 Key 时，可在仓库根目录运行：

```powershell
$llmDir = 'experiments/exp02_llm_entity_recognition'
$env:LLM_API_KEY = [Environment]::GetEnvironmentVariable('EXP02_DEEPSEEK_API_KEY', 'User')
try {
    & .venv/Scripts/python.exe -B "$llmDir/run.py" --base-url https://api.deepseek.com --model deepseek-flash --chunk-size 260 --prompt "$llmDir/prompt_precision.txt" --output "$llmDir/outputs/deepseek_v41_flash_1017_precision_remaining25"
} finally {
    Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue
}
```

| 固定 25 篇，独立抽取 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek 原提示 | 469 | 164 | 41 | 74.09% | 91.96% | 82.06% |
| DeepSeek 严格提示 | 450 | 97 | 60 | 82.27% | 88.24% | 85.15% |
| v7 对照 | 467 | 20 | 43 | 95.89% | 91.57% | 93.68% |

新提示净减 67 个未匹配项，净少命中 19 个参考项。剔除的预测包括「主入口」「女神广场租车点」「芦苇荡」，新增漏识包括「净月潭大坝」「泰山站」。独立 F1 提高 3.09 个百分点。新提示的候选用于 v7 复核补漏时，F1 从 90.71% 升到 92.54%。提示修改参考了这批语料的错误类型，成绩用于固定集开发比较。 [严格提示结果](outputs/deepseek_v41_flash_1017_precision_remaining25/evaluation.json)

## 双提示候选复核

先取原提示和严格提示各自独立抽取的候选并集，再请 DeepSeek 对每个候选判断游览范围、命名和边界。模型只返回要剔除的候选编号，保留下来的名称和跨度来自先前的原文定位。复核阶段读取两个独立抽取产物和原文，评分阶段读取参考标注。

`--evidence document` 提供全文，每批至多 32 个候选。`--evidence excerpts` 为每个候选提供至多 3 处原文片段，单处取名称前后各至多 75 字，每批至多 12 个候选。逐篇产物记录候选编号及剔除记录。

```powershell
$llmDir = 'experiments/exp02_llm_entity_recognition'
$env:LLM_API_KEY = [Environment]::GetEnvironmentVariable('EXP02_DEEPSEEK_API_KEY', 'User')
try {
    & .venv/Scripts/python.exe -B "$llmDir/review_candidates.py" "$llmDir/outputs/deepseek_v41_flash_1017_short_context_remaining25" "$llmDir/outputs/deepseek_v41_flash_1017_precision_remaining25" --evidence excerpts --output "$llmDir/outputs/deepseek_v41_flash_1017_excerpt_review_remaining25"
} finally {
    Remove-Item Env:LLM_API_KEY -ErrorAction SilentlyContinue
}
```

| 固定 25 篇，独立方法 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 单次严格提示 | 450 | 97 | 60 | 82.27% | 88.24% | 85.15% |
| 全文复核 | 395 | 44 | 115 | 89.98% | 77.45% | 83.25% |
| 局部证据复核 | 407 | 47 | 103 | 89.65% | 79.80% | 84.44% |
| 双提示与全文复核投票 | 459 | 96 | 51 | 82.70% | 90.00% | 86.20% |
| v7 对照 | 467 | 20 | 43 | 95.89% | 91.57% | 93.68% |

全文和局部复核分别用了 33 和 63 次请求。直接采用复核结论时，精确率提高，但漏掉了更多参考名称。投票保留两种提示均抽出的名称，只有一版抽出的名称须由全文复核确认。投票阶段可以复用已完成的产物，本身无需请求模型。 [全文](outputs/deepseek_v41_flash_1017_document_review_remaining25/evaluation.json) · [局部证据](outputs/deepseek_v41_flash_1017_excerpt_review_remaining25/evaluation.json) · [投票](outputs/deepseek_v41_flash_1017_review_vote_remaining25/evaluation.json)

```powershell
$llmDir = 'experiments/exp02_llm_entity_recognition'
$runs = "$llmDir/outputs"
& .venv/Scripts/python.exe -B "$llmDir/combine_review.py" "$runs/deepseek_v41_flash_1017_short_context_remaining25" "$runs/deepseek_v41_flash_1017_precision_remaining25" --review "$runs/deepseek_v41_flash_1017_document_review_remaining25" --output "$runs/deepseek_v41_flash_1017_review_vote_remaining25"
```

## LLM 候选边界整理

`refine_boundaries.py` 读取独立抽取结果和原文。它排除普通设施泛称、明确的交通设施，以及仅指目标景区本体的全称。它也会拆开相邻的景区门与广场，去掉名称后的「站点」「登山入口」或酒店分店说明，以及题名之前的「石刻」标签。比如「景区正门女神广场」拆成两个原文实体，「红雨川站点」保留为「红雨川」。每项修改都记录在 `boundary_audit.json`。整理阶段只依赖原文和 LLM 候选，评分阶段另读取参考标注。

| 固定 25 篇，独立方法 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 单次严格提示 | 450 | 97 | 60 | 82.27% | 88.24% | 85.15% |
| 单次严格提示 + 边界整理 | 465 | 47 | 45 | 90.82% | 91.18% | 91.00% |
| 双提示与全文复核投票 | 459 | 96 | 51 | 82.70% | 90.00% | 86.20% |
| 投票 + 边界整理 | 474 | 44 | 36 | 91.51% | 92.94% | 92.22% |
| v7 对照 | 467 | 20 | 43 | 95.89% | 91.57% | 93.68% |

对投票结果整理后，保留此前全部匹配项，找回 15 项，移除 53 项未匹配预测，同时新增 1 项未匹配预测「富蓝特·和酒店」。后处理无需额外 API 调用。规则来自这批文本上的错例，包含对普通设施和边界的归纳，结果用于开发集比较。 [严格提示整理](outputs/deepseek_v41_flash_1017_precision_boundary_remaining25/evaluation.json) · [投票结果整理](outputs/deepseek_v41_flash_1017_boundary_remaining25/evaluation.json)

```powershell
$llmDir = 'experiments/exp02_llm_entity_recognition'
$runs = "$llmDir/outputs"
& .venv/Scripts/python.exe -B "$llmDir/refine_boundaries.py" "$runs/deepseek_v41_flash_1017_review_vote_remaining25" --output "$runs/deepseek_v41_flash_1017_boundary_remaining25"
```

## 黄山迁移评测

用冻结的 DeepSeek Flash 提示词、260 字窗口、全文复核、投票和边界整理，对 `sample_v1` 中的黄山官方线路 `HS_OFF_001` 和游记 `HS_NOTE_001` 做评测。使用历史归档中的 36 个 POI 参考项，按篇、类型和去空白名称匹配。参考为历史助手初标，待人工复核。 [输入](outputs/huangshan_transfer/input.json) · [逐项评测](outputs/huangshan_transfer/evaluation.json)

| 黄山两篇 | TP | FP | FN | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 原提示 | 33 | 8 | 3 | 80.49% | 91.67% | 85.71% |
| 严格提示 | 30 | 3 | 6 | 90.91% | 83.33% | 86.96% |
| 全文复核 | 27 | 2 | 9 | 93.10% | 75.00% | 83.08% |
| 双提示投票 | 30 | 4 | 6 | 88.24% | 83.33% | 85.71% |
| 严格提示 + 边界整理 | 29 | 2 | 7 | 93.55% | 80.56% | 86.57% |
| 投票 + 边界整理 | 29 | 3 | 7 | 90.62% | 80.56% | 85.29% |

边界整理排除了「云谷寺索道」「玉屏索道」，也把历史参考保留的「西海大峡谷北入口」误截成了「西海大峡谷北」。严格提示还漏了「前山」「后山」及官方线路远观段的「光明顶」「飞来石」。本次未用黄山错例修改方法。黄山归档 v2 使用本景区词表，且其词表与参考同源，POI 的 100% F1 属于历史样本上的结果。

## 根据黄山错例修正路线口径

修正版保留「北入口」等方向性出入口的完整名称，排除「索道下端」等交通设施。对带有明确路线动词的相对方位分区，允许从原文补回独立节点。例：「经北坡」「（东坡）上，西坡下」中的方位词可标，普通眺望描述和完整地名中的同形短词不切出。

| 同一方法前后对照 | 黄山精确率 | 黄山召回率 | 黄山 F1 | 原 25 篇 F1 |
|---|---:|---:|---:|---:|
| 投票 + 旧边界整理 | 90.62% | 80.56% | 85.29% | 92.22% |
| 投票 + 修正后处理 | 97.06% | 91.67% | 94.29% | 92.22% |
| 严格提示 + 路线细则 + 修正后处理 | 100.00% | 97.22% | 98.59% | 90.42% |

前两行复用原来的 LLM 投票候选，只对比本地后处理。第三行把 `route_scope_addendum.txt` 附在严格提示之后，单次抽取后做整理。附加细则允许线路明确列出的具名远观景点，黄山找回「光明顶」「飞来石」，剩余一项未匹配参考「汤口」。该提示在原 25 篇低于投票方案，保留为可选实验。黄山已经用于本轮改进，修正后成绩属于开发复测。 [黄山结果](outputs/huangshan_route_scope/evaluation.json) · [原 25 篇，投票后处理](outputs/deepseek_v41_flash_1017_route_boundary_remaining25/evaluation.json) · [原 25 篇，路线提示](outputs/deepseek_v41_flash_1017_route_scope_refined_remaining25/evaluation.json)

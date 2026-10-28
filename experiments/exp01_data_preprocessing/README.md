# 景区指南数据采集与预处理

`selected_v2`已完成30篇纯文本预处理：泰山、张家界武陵源、净月潭各5篇官方路线和5篇携程游记。清洗结果共34,064个非空白字符，660个保留文本块。方法和评分项证据见[项目1报告](../../reports/exp01_report.md)。

正式清洗结果已纳入Git，拉取后可以直接读取`data/processed/full/selected_v2/dataset.json`。下方命令用于重新运行整个采集与处理流程；离线重建需要交接包中的原始HTML快照，仅运行下游项目不需要重新采集。

## 环境与命令

Python 3.10+，依赖`lxml==6.1.1`；本次实际使用Python 3.12.14。以下命令从仓库根目录运行，采集和清洗不调用大模型、不需要密钥。PowerShell中文输出可先设置`$env:PYTHONIOENCODING='utf-8'`。

```bash
python -m pip install -r experiments/exp01_data_preprocessing/requirements.txt
python experiments/exp01_data_preprocessing/src/capture_selected_sources.py --offline
python experiments/exp01_data_preprocessing/src/preprocess_selected.py
python experiments/exp01_data_preprocessing/src/verify_selected.py
```

上例使用数据包中的HTML快照。首次在线获取时去掉`--offline`；采集器默认复用缓存，仅`--refresh`重新联网，请求开始间隔至少2秒。失败返回非零，不把错误页当正文。原站内容更新时，字数和范围配置可能需要重新核查；离线复现以本次快照为准。

仅运行测试：

```bash
python -m unittest discover -s experiments/exp01_data_preprocessing/tests -v
```

本地已执行20项测试，无失败、错误或跳过。缺少数据包时，依赖语料的测试会明确跳过；`verify_selected.py`要求所有检查不跳过，在独立目录重新提取、清洗并比较文件，本次64个输出均字节一致。

## 输入与输出

| 路径 | 用途 |
|---|---|
| `data/metadata/selected_v2_sources.json` | 30篇来源、作者/日期、正文XPath、选文依据 |
| `data/metadata/selected_v2_scope_rules.json` | 逐篇范围、块指纹、截断锚点、保护证据与原文疑点 |
| `data/downloads/selected_v2/` | 30份HTML响应及HTTP元数据，Git忽略 |
| `data/raw/full/selected_v2/` | 30份正文HTML、完整采集文字、来源和哈希，Git忽略 |
| `data/processed/full/selected_v2/dataset.json` | 正式统一输入，另提供同内容JSONL |
| 同目录`texts/`、`audit/`、`before_after_examples.json` | 30份TXT、30份逐块审计、真实变化示例 |
| `data/metadata/selected_v2_quality_report.json` | 数量、缺失、重复、格式、长度及日期冲突，无全文 |
| `data/metadata/selected_v2_verification.json` | 测试与离线复现证据 |

`verify_selected.py`默认将复现临时文件和完整日志写入被Git忽略的`data/processed/full/selected_v2_replay/`，可用`--replay-dir`指定另一独立目录。其他路径参数见各脚本`--help`。

## 清洗流程

1. 按定向来源清单批量采集，用XPath定位正文，排除脚本与网页头尾。保存完整快照，以便复核提取是否丢字。
2. `text_blocks.py`提取有序文字块，忽略图片内容和alt。逐篇配置保留目标景区主体及相关出入交通、住宿背景，排除其他景区独立章节；11篇做了范围选择。
3. `preprocess_selected.py`执行NFC、换行与水平空白归一化，移除技术控制符、BOM、零宽空格及正文网址；只合并重复中文逗号，保留路线符号、星级、表情、时长、原日序、代词、否定和条件。
4. 精确删除播放器占位`00:00/00:00`、无信息占位文本；仅对图注去重，保留叙述中的重复到访和有信息的文字图注。
5. 校验必填/可空字段、日期、快照与正文哈希。详情“发布”标签优先，候选日期冲突保留。原文事实疑点记录而不改写。
6. 导出JSON、JSONL、TXT、块偏移与审计，检查3×(5+5)、全文重复、近重复、格式残留、块内清洗幂等及保护证据。硬检查失败时不输出新的正式数据，并返回非零。

字数均为非空白Unicode字符。70,488字符原始正文先选取34,787字符景区范围，再清理到34,064字符；35,701字符的范围排除与723字符的清洗删减分开统计。正文网址、控制字符、NFC变化等规则在本批未命中时计0，不用合成测试冒充真实噪声。

范围配置绑定文字块内容与顺序。正文变化时脚本明确失败，需要重新审核范围，不能关闭指纹检查。配置由助手逐篇检查制定，不是学生已完成人工实体/关系标注的声明。

## 原样本与历史调查

`src/preprocess.py`只重建原6条`sample_v1`，保持原接口兼容，不用于本批30篇。`probe_sources.py`、`collect_sources.py`保留作前期来源调查。正式入口为上方三个脚本。

当前只处理网页文字，不开展图片下载、OCR或读图补充。`inventory_images.py`及`requirements-images.txt`属于已取消方案的历史记录，不是当前运行依赖；没有据图补造路线和时间。

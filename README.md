# DocSync-AI

面向 Python 开源项目的代码—文档一致性静态检测工具。

> 当前版本为 Phase 5：在稳定检测引擎与 Web 原型之上增加冻结的 controlled benchmark、统一指标计算、定位准确率、性能统计和真实项目案例验证。

## 项目背景

项目持续迭代时，代码签名和默认值常常已经改变，README、API 示例或命令说明却没有同步。DocSync-AI 将代码事实和文档事实结构化后进行显式比对，使问题可定位、可解释、可复现。

本系统不是简单的 LLM Wrapper。完整路线规划为：

```text
静态结构解析 -> 文档信息抽取 -> 实体标准化 -> 确定性实体对齐
             -> 显式一致性规则 -> 可解释置信度 -> 受约束 AI 语义复核
```

## 核心特点

- 只使用静态分析，不导入或执行被分析项目代码。
- Python AST 支持模块、类、函数、异步函数、方法、参数、默认值和 `argparse.add_argument()`。
- Markdown 支持标题、段落、inline code、fenced code block、Python 调用、CLI 命令和配置代码块。
- 配置解析支持 JSON、TOML，以及常用嵌套映射形式的 YAML/YML。
- 对齐结果包含类型、0～1 分数和证据；同分歧义不会强行选取实体。
- `DS001` 只检测不存在的关键字参数或明确参数表中的名称漂移；位置实参变量名不会参与比较。
- `DS002` 只检测文档明确声明的默认值与代码默认值不一致；示例主动传值不会被当作默认值。
- `DS003` 检测 fenced CLI 命令中不存在的 argparse 选项。
- `DS004` 检测 fenced 配置块中不存在的静态配置路径。
- `DS005` 检测 fenced Python 示例中的缺失必需参数、位置参数过多和重复赋值。
- `CONFIRMED` 与 `NEEDS_SEMANTIC_REVIEW` 分开统计，候选项不计入确定错误数量。
- 置信度取“对齐强度”和“规则证据上限”中的较低值，并在 JSON 中给出计算证据。
- AI 只复核 DS001 参数语义候选，返回 `CONSISTENT`、`INCONSISTENT` 或 `UNCERTAIN`。
- `CONSISTENT` 候选被消解；达到阈值的 `INCONSISTENT` 候选升级为 AI 来源 Finding；其余进入人工复核。
- Provider 与业务逻辑解耦，内置离线 Mock 和 OpenAI-compatible 实现，并提供严格 Schema、有限重试、缓存和失败降级。
- 仓库文本始终按不可信数据处理；外部 Provider 默认阻断敏感来源文件，并在发送前裁剪、脱敏上下文。
- FastAPI Web 界面提供本地路径、受限 HTTPS Git 仓库和内置 Demo 三种入口。
- 结果页显示统计卡、五类问题中文解释、事实对照、语义候选、修复建议和前端筛选。
- JSON 与 Markdown 报告可直接下载；Web 不会修改被分析仓库。
- `benchmark-v1` 提供 60 个确定性正负案例和 24 个人工标注语义案例。
- Evaluator 自动计算 TP/FP/FN/TN、Precision、Recall、F1、Macro F1、定位准确率和耗时分布。

## 架构

```text
Python 文件 ----PythonParser----+
配置文件 ----ConfigParser-------+--> EntityAligner --> Rule Engine --> Finding/Candidate --> Reports
Markdown -----MarkdownParser----+                         |
                                                          +--> ConfidenceScorer
                                                          +--> DS001 Candidate --> Semantic Reviewer
CLI / Web -----------------------------> Analysis Service --------------------^
```

核心源码位于 `src/docsync_ai`：

- `models/`：统一实体模型。
- `parsers/`：Python AST、Markdown 与静态配置解析。
- `aligners/`：标识符归一化和确定性实体对齐。
- `rules/`：DS001～DS005 一致性规则。
- `scoring/`：可解释置信度上限与计算证据。
- `semantic/`：Provider、严格返回结构、最小化 Prompt、安全过滤、缓存与复核编排。
- `services/`：CLI 与 Web 共用的唯一分析流程。
- `reports/`：JSON Schema v3.0 与可读 Markdown 报告。
- `web/`：FastAPI、Jinja2 模板以及少量原生 CSS/JavaScript。
- `benchmark/`：冻结数据集生成、评测、结果导出、图表和真实项目案例工具。
- `cli.py`：`analyze` 与 `web` 命令入口。

## 环境与安装

要求 Python 3.11 或以上。Web 运行依赖 FastAPI、Jinja2 和 Uvicorn。

```powershell
cd 'D:\AI+开源主题赛\02_项目源码\docsync-ai'
..\docsync-ai.venv\Scripts\python.exe -m pip install -e .
```

开发测试额外使用 pytest 和 HTTPX：

```powershell
..\docsync-ai.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 运行

安装后执行：

```powershell
docsync-ai analyze .\examples\demo_project --output .\检测结果.json
```

也可以不安装包，直接指定源码路径：

```powershell
$env:PYTHONPATH = 'src'
..\docsync-ai.venv\Scripts\python.exe -m docsync_ai.cli analyze .\examples\demo_project
```

未指定 `--output` 时 JSON 写入标准输出；指定后会创建 UTF-8 JSON 文件。

AI 默认关闭，行为与 Phase 2 相同：

```powershell
docsync-ai analyze .\examples\demo_project --ai off --output .\检测结果.json
```

使用 OpenAI-compatible Provider 前，通过环境变量配置，不要把真实值写入仓库：

```powershell
$env:DOCSYNC_AI_API_KEY = '<your-key>'
$env:DOCSYNC_AI_BASE_URL = 'https://your-endpoint.example/v1'
$env:DOCSYNC_AI_MODEL = 'your-model'
docsync-ai analyze .\examples\demo_project --ai review --output .\检测结果.json
```

可选的 `DOCSYNC_AI_TIMEOUT` 单位为秒。缺少配置或调用失败时，确定性结果仍会输出，相关候选安全降级为 `NEEDS_MANUAL_REVIEW`。离线演示和自动测试使用 `--ai-provider mock`。

## Web 界面

```powershell
docsync-ai web
```

启动后访问 `http://127.0.0.1:8000`。首页可直接点击“体验示例检测”，也可输入本地目录或受支持平台的 HTTPS Git 仓库地址。AI 默认关闭；`Demo / Mock` 会被明确标注为离线模拟结果。

结果页提供：

- 扫描文件和实体统计、风险分布、Confirmed Finding 与 Semantic Candidate 数量。
- DS001～DS005 中文说明、代码/文档位置、事实对照和修复建议。
- 风险、规则类型和状态筛选。
- JSON 与 Markdown 报告下载。

## Benchmark

生成并运行 `benchmark-v1`：

```powershell
..\docsync-ai.venv\Scripts\python.exe -m docsync_ai.benchmark.runner
```

Ground Truth 和案例位于 `D:\AI+开源主题赛\03_测试与评测\benchmark`。确定性案例按 DS001～DS005 各 12 个组织，每类正例和负例各 6 个。评测输出包含 JSON、CSV、Markdown 和简单 SVG 图表。

Ground Truth 建立后会通过版本与内容校验保持冻结。真实 AI Provider 未配置时，LLM-only 和 Hybrid AI 实验明确标记为 `NOT RUN`，不会使用 Mock 数据替代。

## Demo

`examples/demo_project` 包含五个可确认问题：

1. 代码函数参数为 `data_path`，文档错误地使用关键字参数 `path=`。
2. 代码中 `epochs` 默认值为 `50`，文档声明为 `100`。
3. 文档 CLI 使用不存在的 `--model`，代码实际为 `--model-path`。
4. 文档配置使用 `training.batch`，实际路径为 `training.batch_size`。
5. 文档调用 `train()`，缺少必需参数 `data_path`。

参数表中的 `path`、`dataset_file` 和 `source_reference` 是三个独立的 `NEEDS_SEMANTIC_REVIEW` 候选。Mock 演示依次模拟 `CONSISTENT`、`INCONSISTENT` 和 `UNCERTAIN`：一个候选被消解，一个升级为 AI Finding，一个保留人工复核。Demo 还包含使用局部变量 `source_path` 进行位置传参的正确调用。

## 测试

```powershell
..\docsync-ai.venv\Scripts\python.exe -m pytest --basetemp='D:\AI+开源主题赛\99_临时文件\pytest_local'
```

测试覆盖数据模型、解析与规则、AI 安全边界、统一分析服务、Web 首页、Demo、结果渲染、错误处理和两类导出。
`--basetemp` 将测试临时文件留在本项目总目录内；在其他安装位置使用时可换成自己的临时目录。

## 安全边界

- 分析器只读文件并调用解析器，不执行目标项目脚本。
- 默认跳过 `.git`、`.venv`、`__pycache__`、`node_modules`、构建目录等。
- AI 只收到单个候选及少量必要上下文，不发送完整仓库、完整 README 或无关配置。
- README、注释和代码片段均作为不可信数据封装在 JSON 中，不执行其中命令，也不访问其中 URL。
- `.env`、密钥、私钥和明显凭据路径不会发送到外部 Provider；缓存不保存 API Key 或 Token。
- Git URL 仅接受 GitHub、GitLab 和 Gitee 的无凭据 HTTPS 地址，并通过参数数组调用 `git clone --depth 1`；目标固定在比赛临时目录。
- 请勿把 `.env`、令牌、私钥或凭据文件提交到仓库；`.gitignore` 已覆盖常见敏感文件。

## Benchmark 与实验结果

完整 Ground Truth Benchmark、Precision/Recall/F1 和三组对比实验不属于 Phase 1，尚未产生正式实验结论。当前 Demo 和 pytest 仅验证核心链路。

## 开源资源与 AI 使用

Phase 4 Web 使用 FastAPI、Starlette、Jinja2 和 Uvicorn；开发测试使用 pytest 与 HTTPX，构建使用 setuptools。依赖版本、来源、许可证以及 AI 辅助开发记录将在比赛文档阶段持续维护并按官方要求披露。

项目许可证尚未确定，因此当前未创建 `LICENSE`，也不对外宣称具体授权条款。

## 当前限制与未来计划

- 仅支持 Python、Markdown 和静态 JSON/TOML/YAML 配置。
- YAML 解析器刻意只支持常见嵌套映射，不宣称完整 YAML 规范兼容。
- 同名函数、多个 argparse parser 或多个配置文件导致范围不明确时，会生成候选或保守跳过。
- 第一版 AI 复核仅支持 DS001 参数语义候选；DS002～DS005 仍完全由确定性规则处理。
- 模型返回的 confidence 仅是工程置信信息，不代表经过校准的准确率或概率。
- OpenAI-compatible 接口实现面向常见 `/chat/completions` JSON 格式，不保证兼容所有厂商扩展。
- Web 报告暂存在当前服务进程内，服务重启后需要重新检测。
- Git 导入要求本机安装 Git 并能访问目标平台；没有实现认证仓库导入。
- 尚无自动修改仓库、完整 Benchmark 或 CI。

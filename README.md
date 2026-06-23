# auto-research-agent

一个支持本地 Ollama 与云端 Google Gemini 的小型研究循环助手：`Draft -> Review -> Revise -> Judge`。
适合做学术研究规划草案、迭代改写与快速评分。

详细新手说明请先看：`docs/USER_GUIDE.md`。
开发、测试和架构说明请看：`docs/DEVELOPER_GUIDE.md`。

## 你只需要知道这几件事

- 主要输入文件：`projects/example/task.md`
- 启动前先做一次快速检查：
  - `make diagnostic`
- 正常有界运行：
  - `make run`
- 文献综述模式（本地确定性，不调用模型）：
  - `make survey`
- 推荐默认模型：
  - `qwen3:8b`
- 稳定回退模型：
  - `llama3.1:8b`

## 快速开始

```bash
git clone <repo-url>
cd auto-research-agent
cp config.example.yaml config.yaml
make install-dev
ollama pull qwen3:8b
# 可选强化模型
ollama pull qwen3:14b
ollama pull deepseek-r1:8b
# 保留稳定回退
ollama pull llama3.1:8b
make diagnostic
make run
```

## Friend Quickstart / 朋友快速开始

新朋友拿到仓库后，优先跑一条命令：

```bash
git clone <repo-url>
cd auto-research-agent
make bootstrap
```

`make bootstrap` 会检查 `python3`、`make` 和 `ollama`，在缺少本地配置时复制
`config.example.yaml` 到 `config.yaml`，创建 `.venv`，安装依赖，检查推荐模型
`qwen3:8b`，然后跑一次 `make diagnostic`。

如果还没下载推荐模型，先执行：

```bash
ollama pull qwen3:8b
make bootstrap
```

已有 `config.yaml` 不会被覆盖。脚本会从当前仓库位置自动推断路径，不依赖任何个人本机目录。

## 输入文件说明

- `projects/example/task.md`：你的研究任务（必填，最小输入）
- `projects/<project>/memory.md`：历史上下文记忆（可选，程序会自动维护）
- `config.example.yaml`：安全示例配置
- `config.yaml`：本地运行参数（复制示例后生成，不提交）

## 配置安全检查

第一次运行前先创建本地配置：

```bash
cp config.example.yaml config.yaml
```

启动 CLI 或 UI 时会先校验 `config.yaml`。未知字段、错误类型、超出范围的数值、无效
URL 或无效项目名会直接报出具体字段，避免运行到一半才失败。当前推荐格式是嵌套的
`model:` 配置；兼容旧格式 `model: qwen3:8b`，也兼容旧的顶层 `temperature` 和
`timeout_seconds`，但嵌套 `model:` 里的值会优先生效。`model.max_prompt_chars`
用于在本地模型收到过长 prompt 前快速失败，避免反复等待长时间 Ollama 超时。

`topic:` 配置决定通用提示词收到的项目主题上下文。当前仓库里的 `projects/example` 是示例
项目；如果换成新研究方向，请新建 `projects/<name>/`，修改 `project_name`，并同步更新
`topic.title`、`topic.description` 和 `topic.keywords`。

`drafting_mode` 控制每轮 Draft 如何使用上一轮上下文，默认 `best_guided` 保持原行为。
也可以用 CLI 临时覆盖：

```bash
make run ARGS="--drafting-mode fresh_from_task_with_review"
make run ARGS="--drafting-mode continue_from_previous_draft"
```

## 模型建议（Ollama）

- `qwen3:8b`：推荐默认模型（当前默认值），速度和质量平衡
- 如果已经安装，可尝试更小的本地模型：
  - `llama3.2:3b`
  - `phi3:mini`
  - `qwen2.5:3b`
  - `gemma2:2b`

模型切换（CLI 覆盖）示例：

```bash
make run ARGS="--model qwen3:8b"
make diagnostic ARGS="--model llama3.2:3b"
make run ARGS="--model phi3:mini"
```

## 云端 Gemini

图形界面现在可以在 `Model provider` / `模型来源` 中选择 `Local Ollama` 或
`Cloud Gemini`。本地模式保持原来的 Ollama 模型刷新、拉取、删除、健康检查和运行流程；
云端模式不会查询 Ollama，也不要求本机安装本地模型。

推荐通过环境变量提供 Gemini API key：

```bash
export GEMINI_API_KEY="..."
make diagnostic ARGS="--provider gemini --model gemini-3.5-flash"
```

UI 里的 Gemini password 输入框只用于当前 Streamlit session 和本次启动的子进程，不会保存到
`config.yaml`、命令行、运行 meta、checkpoint 或日志。点击 `Save Cloud Model as Default`
只会保存 provider、模型名和 API key 环境变量名。

Cloud Free Runner 会按免费额度做模型发现、profile、串行 pacing 和重试。当前 profiling 后的
长跑推荐是 `gemma-4-26b-a4b-it`；质量推荐是 `gemini-3.5-flash`，但它在免费额度下可能进入
backoff。零成本长时间运行优先用 `Auto: best zero-cost long-run` 或
`Volume free: high-TPM/Gemma or Flash-Lite`，`Quality free: Gemini 3.5 Flash` 更适合短的高质量测试。
遇到免费层 429 时，backoff、checkpoint 和之后 resume 是预期行为，不代表功能失败。

Benchmark 运行请优先使用安全 preset，而不是直接把免费 Gemini 跑成 25 轮长测：

```bash
make continuous ARGS="--provider gemini --benchmark-preset free_smoke"
make continuous ARGS="--provider gemini --benchmark-preset free_eval"
make continuous ARGS="--provider gemini --benchmark-preset paid_benchmark"
```

Preset 轮数：`free_smoke=4`、`free_eval=5`、`paid_benchmark=25`、`stress_test=50`。
启动前 CLI 会估算每轮 LLM calls 和总 calls；Gemini 下如果超过保守低免费额度，会打印 warning。
连续 provider quota/rate-limit 失败默认 2 轮后自动停止，stop reason 为
`PROVIDER_QUOTA_EXHAUSTED`，避免继续生成大量无意义失败轮。

当前第一版云端 provider 只支持 Google Gemini。不支持 Vertex AI、OpenAI compatibility、
streaming、tools/search/function calling 或 Interactions API 迁移。真实 Gemini 在线测试需要
你下一轮提供 API key、要测的模型（例如 `gemini-3.5-flash`）和运行模式，建议先跑
Diagnostic。

## 先看哪个输出

先看：`projects/example/best_output.md`  
再看：`projects/example/runs/<run_id>/round_xx/` 里的 4 个阶段文件。
如果要复现实验环境，再看同一 run 目录下的 `run_config.json`，其中记录 provider/model、
轮数和运行时配置、topic 快照、prompt 文件 SHA-256、Git commit、开始/结束时间、停止原因和
resume eligibility。

## 常用命令

- 安装开发与 CI 检查工具
  - `make install-dev`
- 本地完整检查（格式、lint、导入、测试）
  - `make check`
- 自动格式化 Python 代码
  - `make format`
- 基础诊断（1 轮、快速验证）
  - `make diagnostic`
- 正常有界运行（按 `max_rounds` 停止）
  - `make run`
- 会话模式（包含 objective/plan/report）
  - `make session`
- 文献综述模式（收集、去重、主题/缺口分析、相关工作草稿）
  - `make survey`
- 连续运行
  - `make continuous`
- 从检查点恢复
  - `make resume`
- 启动本地图形界面
  - `make ui`
  - 或运行项目自带脚本：`scripts/start_ui.sh`

直接调用入口也可以使用：

```bash
.venv/bin/python -m src.main --diagnostic
.venv/bin/python -m src.main --survey
.venv/bin/auto-research-agent --diagnostic
```

## Literature Survey Mode

Survey mode turns the selected project into a local literature-survey workspace. It scans existing
project files and saved run outputs, normalizes paper metadata, deduplicates papers, extracts
themes/gaps/future directions, and writes:

- `projects/<project>/survey/survey_report.md`
- `projects/<project>/survey/paper_metadata.json`
- `projects/<project>/survey/related_work.md`
- `projects/<project>/survey/survey_manifest.json`

It does not call Ollama or Gemini. Configure source scanning under `literature_survey:` in
`config.yaml`. Full docs: `docs/literature_survey_mode.md`.

## CI / 开发检查

GitHub Actions 会在推送到 `master`、`codex/**` 分支以及提交到 `master` 的 PR 时运行。
CI 使用 Python 3.10 和 3.13，执行和本地完整检查相同的步骤：

```bash
make check
```

这个命令会检查 Ruff 格式、Ruff lint、基础导入安全和测试套件。CI 不会启动 Ollama
或运行需要本地模型的研究流程。

## Graphical UI

- 启动：
  - `cd auto-research-agent`
  - `make ui`
  - 或直接运行：`scripts/start_ui.sh`
- 路径检查：
  - UI 侧边栏会显示 `App root` 为 `<repo>`，避免直接暴露本机绝对路径
  - 需要排查启动目录时，可展开 `Advanced paths` 查看详细路径
- 界面语言：
  - 在侧边栏 `Language` 选择 `English` 或 `中文`
  - 语言选择会保存在当前 Streamlit 会话中，不会改动 `config.yaml`
- 显示主题：
  - 在侧边栏 `Theme` 选择 `Day Mode` 或 `Dark Mode`
  - 主题会覆盖主界面、侧边栏、按钮、输入框、日志、代码块和状态提示
- 选择模型：
  - 先在 `Model provider` / `模型来源` 选择 `Local Ollama` 或 `Cloud Gemini`
  - UI 会自动读取本机 Ollama 已安装模型，并显示在 `Installed Ollama models`
  - 点击 `Refresh models` / `刷新模型` 可重新读取本机模型列表
  - 从下拉框选择模型后，运行按钮会带上 `--model <name>`
  - 如果列表里没有你的模型，可在 `Manual model name` / `手动输入模型名` 输入完整模型名
  - 手动输入非空时优先使用手动模型；否则使用下拉框选择
- 拉取模型：
  - 在 `Pull model by name` 输入模型名，点击 `Pull Model`
- 删除模型：
  - 选择已安装模型并勾选确认，点击 `Delete Selected Model`
  - 若该模型正被运行任务使用，UI 会阻止删除
- 输入任务：
  - 如果 `config.yaml` 里的 `project_name` 存在，项目选择器默认打开该项目；否则才回到公开安全的 `example` 项目
  - 项目路径和输出路径会显示为 `projects/<project>` 这类相对路径
  - 在 UI 的 `task.md` 和 `memory.md` 文本框编辑，然后点击 `Save Input`
- 开始运行：
  - `Run Diagnostic` / `Run Normal` / `Run Continuous`
  - UI 会把当前 provider 和模型自动传给后端（例如 `--provider ollama --model qwen3:8b`
    或 `--provider gemini --model gemini-3.5-flash`）
  - Gemini password 只通过子进程环境变量传递，不会进入命令行或 meta JSON
- 运行项目测试：
  - 在 `Project Tests` 里点击 `Run Tests`
  - 会执行当前环境的 `pytest -q`，并在页面显示通过/失败和完整输出
- 安全停止：
  - 点击 `Pause / Stop Safely`（创建 `STOP_REQUESTED`，后端在安全点退出）
- 恢复：
  - 点击 `Resume`（等价 `.venv/bin/python -m src.main --resume`）
- 看结果：
  - 先看 `projects/example/best_output.md`
  - 再看 `projects/example/runs/<run_id>/round_xx/`
  - 复现信息看 `projects/example/runs/<run_id>/run_config.json`
  - 实时状态看 `projects/example/checkpoint.json`
  - 实时日志看 `projects/example/run.log`

推荐模型：

- `qwen3:8b`：默认质量均衡
- 如果已安装，可尝试较小模型：`llama3.2:3b`、`phi3:mini`、`qwen2.5:3b`、`gemma2:2b`

模型异常提示：

- 模型未下载：会提示 `Model <name> is not installed. Run: ollama pull <name>`
- Ollama 不可用：会提示 `Ollama is not available ...`
- 没有检测到模型：先运行 `ollama pull qwen3:8b`，或安装适合本机的小模型后刷新列表

## 关于“连续运行 / 安全停止 / 恢复”

- 连续运行：`make continuous`
- 安全停止：
  - `Ctrl+C`
  - 或创建 `projects/example/STOP_REQUESTED`（UI 按钮会自动创建）
- 恢复：`make resume`（读取 `projects/example/checkpoint.json`）
- 进度不会丢：每轮都会写入 `runs/round_xx`，并更新 checkpoint

## 哪些文件不要提交

这些是运行生成物或本地私有文件，默认已被 `.gitignore` 忽略：

- `projects/*/runs/`
- `projects/*/best_output.md`
- `projects/*/score_history.json`
- `projects/*/research_state.json`
- `projects/*/current_plan.md`
- `projects/*/final_session_report.md`
- `projects/*/run.log`
- `projects/*/memory.md`
- `config.yaml`
- 不要提交真实 API key、`.env`、含密钥的本地配置或运行输出
- `projects/*/checkpoint.json`
- `projects/*/interrupted_report.md`
- `projects/*/STOP_REQUESTED`
- `.env` / `.env.*`（保留 `.env.example`）
- `.venv/`

## 推送到 GitHub（稳定版本交接）

```bash
git status
git add .
git commit -m "Add user guide and safe run controls"
git push
```

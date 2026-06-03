# USER GUIDE

这份文档面向第一次使用本项目的人，按“输入 -> 运行 -> 看结果 -> 提交 GitHub”来走。

## 这个项目做什么

它会用本地 Ollama 或云端 Google Gemini 跑一个研究循环：

1. Draft（起草）
2. Review（审查）
3. Revise（改写）
4. Judge（评分）

每轮都会把中间结果落盘，避免只存在内存中。

## 模型选择建议

- `qwen3:8b`：推荐默认模型（当前默认），质量和速度较均衡
- 如果你已经在 Ollama 里安装了更小模型，也可以尝试：
  - `llama3.2:3b`
  - `phi3:mini`
  - `qwen2.5:3b`
  - `gemma2:2b`
- 如果使用云端模式，第一版只支持 Google Gemini，例如 `gemini-3.5-flash`。

## 首次安装

进入项目目录后运行：

```bash
cp config.example.yaml config.yaml
make install-dev
```

这会先创建本地配置，再用 `python3` 创建 `.venv`，并安装运行和测试所需依赖。
`config.yaml` 是本地文件，不应该提交到 Git。

命令行切换模型：

```bash
make run ARGS="--model qwen3:8b"
make diagnostic ARGS="--model llama3.2:3b"
make run ARGS="--model phi3:mini"
```

## config.yaml 配置校验

程序启动时会先检查 `config.yaml`。如果字段名写错、类型不对、数值超出范围、
`ollama_base_url` 不是有效 HTTP/HTTPS 地址，或 `project_name` 不是简单项目文件夹名，
会直接显示具体配置错误并停止。

推荐继续使用当前嵌套格式：

```yaml
model:
  provider: ollama
  name: qwen3:8b
  temperature: 0.3
  timeout_seconds: 300
  gemini:
    api_key_env: GEMINI_API_KEY
    api_key: ""
    models:
      - gemini-3.5-flash
      - gemini-2.5-flash
      - gemini-2.5-pro
      - gemini-2.5-flash-lite
topic:
  title: Example Research Planning Task
  description: A public-safe starter project for learning the local research workflow.
  keywords:
    - research
    - planning
    - methods
    - evaluation
    - risks
```

旧写法 `model: qwen3:8b` 仍可用；旧的顶层 `temperature` 和 `timeout_seconds`
也仍可作为 fallback。若同一项同时出现在顶层和 `model:` 里，以 `model:` 里的值为准。
`topic:` 会传给 Draft / Review / Revise / Judge，让同一套提示词可以服务不同项目。

如果要用 Gemini，推荐通过环境变量提供 key：

```bash
export GEMINI_API_KEY="..."
make diagnostic ARGS="--provider gemini --model gemini-3.5-flash"
```

不要提交真实 API key、`.env` 或写入明文 key 的本地配置。UI 的 Gemini password 输入框只用于
当前会话和本次启动的子进程，不会保存到 `config.yaml`、命令行、运行 meta、checkpoint 或日志。

在 UI 中切换模型：

1. 进入项目目录：`cd auto-research-agent`
2. 第一次使用先安装依赖：`make install-dev`
3. 启动图形界面：`make ui`
4. 也可以直接运行项目脚本：`scripts/start_ui.sh`
5. 在侧边栏确认 `App root` 是当前仓库根目录
6. 在侧边栏 `Language` 选择 `English` 或 `中文`
7. 在侧边栏 `Theme` 选择 `Day Mode` 或 `Dark Mode`
8. 项目选择器默认显示公开安全的 `example` 项目；如需运行自己的项目，再手动选择
   `projects/<name>/`
9. 在 `Model provider` / `模型来源` 选择 `Local Ollama` 或 `Cloud Gemini`
10. 本地模式会自动读取本机 Ollama 已安装模型，并显示在 `Installed Ollama models`
11. 如果刚安装或删除模型，点击 `Refresh models` / `刷新模型`
12. 本地模式可在下拉框选择已安装模型，也可在 `Manual model name` / `手动输入模型名` 输入完整模型名
13. 云端模式可填写 API key 环境变量名、当前 session 的 password 输入框，并选择 Gemini 模型
14. 确认 `Effective model` / `实际使用模型` 或 `Effective cloud model` / `实际使用云端模型`
15. 点击 `Run Diagnostic / Run Normal / Run Continuous / Resume`
16. UI 会自动传参：`--provider <provider> --model <effective_model>`

语言和主题只保存在当前 Streamlit 会话里，不会改写 `config.yaml`。中文界面会保留
Ollama、模型名、命令和文件路径等技术标识，方便按错误提示继续操作。

模型优先级：

1. 手动输入非空时，优先使用手动模型名
2. 否则使用下拉框当前选中的已安装模型
3. 第一次进入页面时，下拉框优先使用当前会话选择，其次使用 `config.yaml` 的 `model.name`
4. 如果默认 `qwen3:8b` 已安装，会优先显示它；否则使用检测到的第一个模型

云端 Gemini 不依赖 Ollama。选择 `Cloud Gemini` 时，即使本机没有 Ollama 或没有本地模型，也不会因此阻塞运行。
当前不支持 Vertex AI、OpenAI compatibility、streaming 或 Google tools/function calling。真实 Gemini 测试需要你提供
API key、模型名和运行模式，建议优先 Diagnostic。

Cloud Free Runner 的 profiling 结果会推荐免费模型。当前长时间零成本运行推荐
`gemma-4-26b-a4b-it`；质量推荐 `gemini-3.5-flash`，但它在免费额度下可能触发 backoff。长跑优先选
`Auto: best zero-cost long-run` 或 `Volume free: high-TPM/Gemma or Flash-Lite`；`Quality free:
Gemini 3.5 Flash` 更适合短的高质量测试。免费层 429 导致的 backoff、checkpoint、`can_resume:
true` 和稍后 resume 是预期行为。

在 UI 中拉取模型：

1. 在 `Pull model by name` / `按名称拉取模型` 输入模型名
2. 点击 `Pull Model` / `拉取模型`
3. 在 `Model operation logs` / `模型操作日志` 查看拉取进度

在 UI 中删除模型：

1. 在删除下拉框选已安装模型
2. 勾选确认框
3. 点击 `Delete Selected Model` / `删除选中模型`
4. 若模型正在被当前运行使用，UI 会阻止删除

常见模型相关错误：

- 未安装模型：
  - `Model <name> is not installed. Run: ollama pull <name>`
- Ollama 未运行或不可用：
  - `Ollama is not available ...`
- 没有检测到模型：
  - 先运行 `ollama pull qwen3:8b`
  - 或安装已知更适合本机的小模型后回到 UI 点击 `Refresh models`

模型检查命令：

```bash
ollama list
ollama run qwen3:8b
```

## 我该把输入写在哪里

核心输入写在：`projects/example/task.md`

可选补充可以从模板创建：

```bash
cp projects/example/memory.example.md projects/<project>/memory.md
```

当前 `projects/example` 是仓库自带示例项目。如果要换主题，可以新建 `projects/<name>/`，
然后在 `config.yaml` 里同步修改 `project_name` 和 `topic:`。

UI 会显示相对项目路径，例如 `projects/example`，避免把本机绝对路径展示到页面上。

- `task.md`：你本次希望研究/回答的问题（必须有内容）
- `memory.md`：历史上下文、限制、已知结论（可空，程序会自动更新）

## 最小输入需要什么

最小只需要：

- `projects/example/task.md` 里有清晰问题描述

其他都可以保持默认。

## 我应该先跑哪个命令

先跑诊断：

```bash
make diagnostic
```

确认本机模型、提示词和文件写入都正常，再跑正式模式。

## 连续运行用哪个命令

```bash
make continuous
```

连续模式会逐轮执行，并在每轮持续写入输出和检查点。

## 如何安全停止

有两种方式：

1. 终端按 `Ctrl+C`
2. 在 Streamlit UI 里点击 `Pause / Stop Safely`（会创建 `STOP_REQUESTED`）

程序会在安全点停止，并生成：

- `projects/example/checkpoint.json`
- `projects/example/interrupted_report.md`

## 如何恢复（resume）

```bash
make resume
```

恢复会读取 `projects/example/checkpoint.json`：

- 从 `last_completed_round + 1` 继续
- 不覆盖已有 round 文件
- 只有更高分时才更新 `best_output.md`

## 输出文件怎么读（先看哪个）

先看：`projects/example/best_output.md`

这是当前最佳版本（按 Judge 分数）。

再看：`projects/example/runs/<run_id>/round_xx/`

每轮有 4 个文件：

- `01_draft.md`
- `02_review.md`
- `03_revised.md`
- `04_judge.md`

阅读顺序建议：`04_judge.md` -> `03_revised.md` -> `02_review.md` -> `01_draft.md`。

## memory.md / best_output.md / score_history.json 怎么理解

- `memory.md`：被持续维护的“研究状态记忆”，会影响下一轮输入。
- `best_output.md`：当前最高分对应的输出，通常是你优先阅读的文件。
- `score_history.json`：每轮评分轨迹、是否提升、是否超时等结构化记录。

## 哪些生成文件不要提交到 GitHub

默认不提交（已在 `.gitignore`）：

- `projects/*/runs/`
- `projects/*/best_output.md`
- `projects/*/score_history.json`
- `projects/*/research_state.json`
- `projects/*/current_plan.md`
- `projects/*/final_session_report.md`
- `projects/*/run.log`
- `projects/*/checkpoint.json`
- `projects/*/interrupted_report.md`
- `projects/*/memory.md`
- `config.yaml`
- `.env` / `.env.*`（保留 `.env.example`）
- `.venv/`

## 推送当前稳定状态到 GitHub

```bash
git status
git add .
git commit -m "Stabilize runtime and improve user documentation"
git push
```

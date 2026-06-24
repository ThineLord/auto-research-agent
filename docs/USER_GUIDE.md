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

## 稳定工作流

稳定里程碑推荐按下面顺序使用：

1. `make bootstrap`：准备新 checkout，并跑一次真实 diagnostic smoke。
2. `make mock`：不调用 provider，写一份确定性 demo run artifacts。
3. `make diagnostic`：调用真实 provider 跑 1 轮 smoke。
4. `make run`：启动普通有界研究 run。
5. `make resume`：从 checkpoint 继续同一个旧 run。
6. `make survey`：不调用模型地生成本地文献综述 artifacts。
7. `--compare-runs`：比较多个 run。
8. `--analyze-run`：检查单个 run。
9. `make ui`：查看 latest metadata、Run analytics dashboard、Run comparison 和 outputs。

新用户第一次演示建议先跑：

```bash
make bootstrap
make mock
make ui
```

然后在 UI 中检查 `Latest run metadata`、`Run analytics dashboard`、`Run comparison` 和
`Output browser`。Mock mode 只适合 demo/CI/docs smoke；真实研究请用 `make diagnostic` 或
`make run`。

命令行切换模型：

```bash
make run ARGS="--model qwen3:8b"
make diagnostic ARGS="--provider ollama --model llama3.2:3b"
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
  max_prompt_chars: 12000
  gemini:
    api_key_env: GEMINI_API_KEY
    api_key: ""
    models:
      - gemini-3.5-flash
      - gemini-2.5-flash
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
drafting_mode: best_guided
```

旧写法 `model: qwen3:8b` 仍可用；旧的顶层 `temperature` 和 `timeout_seconds`
也仍可作为 fallback。若同一项同时出现在顶层和 `model:` 里，以 `model:` 里的值为准。
`model.max_prompt_chars` 用于在本地模型收到过长 prompt 前快速失败；`topic:` 会传给
Draft / Review / Revise / Judge，让同一套提示词可以服务不同项目。

`drafting_mode` 决定每轮 Draft 使用哪些上一轮上下文：

- `best_guided`：默认值，保留当前行为，Draft 可看当前最佳输出和上一轮 Judge 反馈。
- `fresh_from_task_with_review`：每轮从原始 task 重新起草，只参考上一轮 Review/Judge 反馈。
- `continue_from_previous_draft`：每轮基于上一轮 draft/revised 输出继续，并可参考反馈。

CLI 临时覆盖示例：

```bash
make run ARGS="--drafting-mode fresh_from_task_with_review"
make run ARGS="--drafting-mode continue_from_previous_draft"
```

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
8. 如果 `config.yaml` 里的 `project_name` 存在，项目选择器默认显示该项目；否则才显示
   公开安全的 `example` 项目
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
运行后，UI 的 `Latest run metadata` 会集中显示 run_config/run_summary 中的模型、drafting mode、
Git commit、停止原因、最佳分数、修订稿相对上一轮的平均相似度和 artifact 路径；
`Run analytics dashboard` 会用现有 `run_summary.json`、`round_metrics.json` 和
`score_history.json` 展示分数、rubric、相似度/evolution、timeout/error、agent 耗时和估算
token 趋势；缺少旧字段时显示空表或部分图表，不会让 UI 失败。`Output browser` 也可直接打开
`round_metrics.json`。token 指标使用可见 prompt context
和输出长度做保守估算；字段名中的 `estimated_*_tokens` 表示估算值，不代表真实账单 token。
相似度/低变化轮次是基于已生成文本的解释性指标，不改变评分或停止条件。

- `task.md`：你本次希望研究/回答的问题（必须有内容）
- `memory.md`：历史上下文、限制、已知结论（可空，程序会自动更新）

## 最小输入需要什么

最小只需要：

- `projects/example/task.md` 里有清晰问题描述

其他都可以保持默认。

## 我应该先跑哪个命令

先跑诊断：

```bash
make diagnostic ARGS="--provider ollama --model qwen3:8b"
```

确认本机模型、提示词和文件写入都正常，再跑正式模式。

如果你只想整理项目里的论文和相关工作，不需要模型，运行：

```bash
make survey
```

Survey mode 会扫描 `projects/<project>/task.md`、可选 `memory.md`、项目 markdown 和已有
`runs/**/*.md` 输出，生成 `projects/<project>/survey/survey_report.md`、
`paper_metadata.json`、`related_work.md` 和 `survey_manifest.json`。
输出会规范化 DOI/arXiv 标识并在 JSON 中记录缺失作者、年份、venue、URL/DOI/arXiv 的质量计数。

如果你只想做 CI/docs 友好的 demo run，不想安装 Ollama 或配置 Gemini key，运行：

```bash
make mock
make mock ARGS="--max-rounds 1"
```

Mock mode 是确定性的 provider-free workflow：它不会调用 Ollama、Gemini、网络或 API key，
但会写正常 run artifacts，包括 `run_config.json`、`round_metrics.json`、`run_summary.json`、
`checkpoint.json` 和 `score_history.json`。默认只跑 2 轮；传 `--max-rounds` 可以覆盖。
这些 score 和 rubric 是合成 demo 信号，不应当当作真实研究评估。

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
- 不覆盖已完成 round 文件
- 如果下一轮目录不存在或为空，可以继续；如果下一轮目录已存在且非空，会 fail-safe 停止，
  避免覆盖 partial/uncheckpointed 输出
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

如果要复现实验设置，查看：`projects/example/runs/<run_id>/run_config.json`

它记录 provider/model、temperature/top_p/timeout、max rounds 和 runtime 限制、topic 快照、
prompt 文件 SHA-256、Git commit、开始/结束时间、停止原因和是否可 resume。旧 run 如果只有
`run_manifest.json`，工具会以兼容方式读取旧 metadata。
`checkpoint.json`、`run_config.json` 和 `run_summary.json` 还会写 `resume_metadata`：

- `lifecycle_action=start_new_run`：新建 run 目录；如果 `best_output.md` 已存在，当前默认流程可把它作为 previous-best context。
- `lifecycle_action=resume_existing_run`：从 checkpoint 继续同一个 run；下一轮是 `last_completed_round + 1`，已完成轮次文件会保留。

CLI `--resume` 会先打印 resume preview，包括 run id/root、last completed round、next round、
stop reason、是否可 resume、下一轮目录状态和安全动作。UI 的 Resume 区域也显示同样信息，
并会提示缺失、stale checkpoint 或 partial next-round directory。

如果要看本次 run 总览和每轮指标，查看：

- `projects/example/runs/<run_id>/run_summary.json`
- `projects/example/runs/<run_id>/round_metrics.json`

`round_metrics.json` 每轮包含 `agent_io_metrics`，按 `draft`、`review`、`revise`、`judge`
记录是否调用、是否出错、耗时、估算输入字符、输出字符和估算 input/output/total tokens。
每轮还包含 `evolution_metrics`，记录 draft 到 revised 的相似度、revised/judge 相对上一轮的相似度、
变动行数和相邻轮分数差，用于发现重复、低变化或大幅漂移。
`run_summary.json` 汇总 `total_elapsed_seconds`、`total_agent_elapsed_seconds`、
`total_estimated_input_tokens`、`total_estimated_output_tokens`、`total_estimated_tokens`、
`timeout_count`、`error_count`、平均相似度、低变化轮次列表和 Judge rubric 子项均值/最新值/首尾变化。
这些 rubric 汇总只复用 Judge 已返回的结构化子项，不改变总分解析或评分语义。当前不会内置任何厂商价格表；如需成本估算，应在外部基于
这些 token estimate 明确标注价格假设。

如果要比较多个 run：

```bash
.venv/bin/python -m src.main --compare-runs projects/example/runs/<run_a> projects/example/runs/<run_b>
```

也可以在 UI 的 `Run comparison` 区域选择多个 run。比较会显示 run path、provider、model、
drafting mode、max/completed rounds、best/average score、stop reason、timeout/error counts、
agent elapsed seconds、estimated tokens、平均 revised 相似度、低变化轮次数和 rubric 子项均值，
并保持路径为 repo-relative 或 masked。

如果只想检查一个 run，不需要提供对照 run：

```bash
.venv/bin/python -m src.main --analyze-run projects/example/runs/<run_id>
```

`--analyze-run` 不调用模型，会把分数首尾变化、超时/错误、估算 token、相似度和 rubric 摘要组合成一个 JSON。
可加 `--analyze-output projects/example/run_analysis.json` 保存结果。

## memory.md / best_output.md / score_history.json 怎么理解

- `memory.md`：被持续维护的“研究状态记忆”，会影响下一轮输入。
- `best_output.md`：当前最高分对应的输出，通常是你优先阅读的文件。
- `score_history.json`：每轮评分轨迹、是否提升、是否超时、每个 agent 耗时、估算 token、文本 evolution 指标和 Judge rubric 子项（如果可解析）。

## 哪些生成文件不要提交到 GitHub

默认不提交（已在 `.gitignore`）：

- `projects/*/runs/`
- `projects/*/best_output.md`
- `projects/*/score_history.json`
- `projects/*/research_state.json`
- `projects/*/current_plan.md`
- `projects/*/final_session_report.md`
- `projects/*/survey/`
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

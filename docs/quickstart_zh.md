# Auto Research Agent 快速上手指南

## 1. 项目一句话说明

Auto Research Agent 是一个本地优先的研究计划迭代助手：读取 `projects/<project>/task.md` 和 `memory.md`，用 Ollama 模型循环执行 `Draft -> Review -> Revise -> Judge`，把每轮草稿、审查、改写、评分和检查点保存到项目目录里。

## 2. 项目状态

当前项目是一个 Python 包，没有前端构建链，也没有 `package.json`。入口已经比较清楚：CLI 在 `src/cli.py`，兼容入口在 `src/main.py`，Streamlit 页面在 `ui/app.py`，命令集中在 `Makefile`。

已实现的核心能力：

- 基于 Ollama 的本地模型调用，示例配置默认模型是 `qwen3:8b`。
- 四阶段研究循环：draft、review、revise、judge。
- 一轮诊断模式、普通有界模式、连续模式、session 模式、resume 模式。
- 每轮输出落盘到 `projects/pama/runs/<run_id>/round_xx/`。
- `checkpoint.json`、`score_history.json`、`research_state.json`、`best_output.md` 等运行状态文件。
- Streamlit UI：编辑输入、启动运行、暂停、恢复、模型管理、测试按钮、进度日志、输出浏览。

使用前需要注意：

- 首次运行需要复制 `config.example.yaml` 到本地 `config.yaml`。
- `config.yaml`、`projects/*/memory.md` 和运行输出默认不提交。
- resume 依赖本地已有 `checkpoint.json`；新 clone 通常没有可恢复状态。
- 当前可视化主要是运行控制和输出浏览，不是完整实验分析 dashboard。

## 3. 我现在可以做什么

- 跑一个不调用模型的最小单元测试，确认核心循环写文件逻辑还活着。
- 查看已有输出：先读 `projects/pama/best_output.md`，再看对应 run 目录里的 round 文件。
- 打开 Streamlit UI，查看 checkpoint、score history、run log、最新 round 文件。
- 修改 `projects/<project>/task.md` 和 `projects/<project>/memory.md`，然后从 UI 或 CLI 启动新 run。
- 用 `make resume` 从已有 checkpoint 继续，但这会调用本地 Ollama 模型。
- 比较不同 round 的 `01_draft.md`、`02_review.md`、`03_revised.md`、`04_judge.md`。
- 用 `score_history.json` 粗看评分、超时、重复 judge、无效分数、错误轮次。
- 改本地 `config.yaml` 切换模型、轮数、runtime 上限、项目名和 topic。

## 4. 快速启动命令

```bash
git clone <repo-url>
cd auto-research-agent
cp config.example.yaml config.yaml
```

进入项目目录并创建本地配置。

```bash
source .venv/bin/activate
```

激活已有虚拟环境。如果还没有 `.venv`，先运行 `make install-dev`。

```bash
make install-dev
```

创建或更新 `.venv`，并安装运行依赖和测试工具。

```bash
make help
```

查看 Makefile 暴露的全部常用命令。

```bash
.venv/bin/python -m src.main --help
```

查看 CLI 支持的运行模式和参数。

```bash
make format-check
make lint
make import-check
```

检查格式、lint 和模块导入。

```bash
.venv/bin/python -m pytest tests/test_round_loop.py::RoundLoopTests::test_round_loop_writes_outputs_and_keeps_best_score -q
```

运行一个不调用 Ollama 的最小循环 smoke test。

```bash
.venv/bin/python -m pytest tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_progress_resume_and_output_helpers -q
```

运行一个不启动真实 UI 的 UI helper smoke test。

```bash
.venv/bin/python -m pytest -q
```

运行完整测试。

```bash
ollama list
```

查看本机已安装模型。

```bash
make diagnostic
```

运行一轮轻量诊断，会调用 Ollama 生成内容；适合确认模型、提示词、落盘流程是否真实可用。

```bash
make run
```

按 `config.yaml` 的 `max_rounds` 做普通有界运行，会调用 Ollama。

```bash
make continuous
```

连续运行，直到手动停止、超时或外部停止信号；会调用 Ollama，可能很久。

```bash
make resume
```

读取 `projects/pama/checkpoint.json` 继续；会调用 Ollama。

```bash
make ui
```

启动 Streamlit UI，默认打开 `http://localhost:8501`。

```bash
scripts/start_ui.sh
```

等价的 UI 启动脚本，会先检查 `.venv/bin/python` 和 Streamlit 是否存在。

停止方式：

```bash
Ctrl+C
```

停止当前终端里的 CLI 或 Streamlit 服务。

```bash
touch projects/pama/STOP_REQUESTED
```

请求研究循环在安全点停止；UI 的 `Pause / Stop Safely` 按钮也是创建这个文件。

## 5. 输出文件在哪里

当前项目没有顶层 `outputs/` 目录，也没有顶层 `runs/` 目录。实际输出集中在：

- `projects/pama/runs/<run_id>/round_xx/01_draft.md`：每轮 draft。
- `projects/pama/runs/<run_id>/round_xx/02_review.md`：每轮 review。
- `projects/pama/runs/<run_id>/round_xx/03_revised.md`：每轮 revise 后的版本。
- `projects/pama/runs/<run_id>/round_xx/04_judge.md`：每轮 judge 输出。
- `projects/pama/best_output.md`：目前最高 judge 分数对应的 revised 输出。
- `projects/pama/score_history.json`：每轮分数、是否提升、是否超时、是否重复、错误等。
- `projects/pama/research_state.json`：当前 strongest hypothesis、biggest blocker、next experiment、open question。
- `projects/pama/checkpoint.json`：resume 所需状态。
- `projects/pama/run.log`：运行日志和 agent 调用时间。
- `projects/pama/interrupted_report.md`：安全停止或中断后的恢复说明。
- `projects/pama/current_plan.md`：session 模式生成的计划。
- `projects/pama/final_session_report.md`：session 模式最终报告。
- `projects/pama/model_ops.log`：UI 拉取或删除模型时的日志。

建议之后统一方案：

- 保持 `projects/<project>/` 作为唯一项目状态根目录。
- 把所有运行生成物都放进 `projects/<project>/runs/<run_id>/`，根目录只保留索引文件：`checkpoint.json`、`best_output.md`、`score_history.json`。
- 给每个 run 增加 `run_config.json`，记录模型、drafting mode、prompt 版本、开始时间、停止原因。

## 6. 可视化怎么打开

当前只发现一个真正的可视化/页面系统：Streamlit UI。没有发现 HTML 文件、Vite、FastAPI、Gradio、Flask、Dash 或 `web/ui` 目录。

### Streamlit UI

路径：

- `ui/app.py`
- 启动命令：`make ui`
- 备用启动命令：`scripts/start_ui.sh`
- 默认端口：`8501`
- URL：`http://localhost:8501`

展示内容：

- `App root` 路径检查。
- `Quick Actions`：一键运行测试。
- `A. Project selector`：选择 `projects/` 下的项目。
- `B. Input editor`：编辑 `task.md` 和 `memory.md`。
- `C. Run controls`：Run Diagnostic、Run Normal、Run Continuous、Pause / Stop Safely、Resume、Run Tests。
- `Project Tests`：运行 `pytest -q` 并显示输出。
- `Model Management`：列出模型、选择模型、健康检查、保存默认模型、拉取和删除模型。
- `D. Progress panel`：显示 mode、round、stage、best score、PID、model、stop reason、stop signal。
- `E. Live logs panel`：显示 `run.log` 和 `model_ops.log` 尾部。
- `F. Output browser`：浏览 best output、final report、interrupted report、checkpoint、score history、run log、latest round 四阶段文件。

适合什么时候看：

- 开始前：确认项目路径、模型是否安装、输入文件是否正确。
- 运行中：看当前轮数、agent 阶段、是否卡住、日志是否持续更新。
- 停止后：看 checkpoint、score history、best output、最新 round 文件。
- 恢复前：确认 UI 是否提示可从 checkpoint 继续。

重点看：

- `Best score` 是否继续上升。
- `Stage` 是否长时间停在同一个 agent。
- `Stop reason` 是 `MAX_ROUNDS`、`USER_STOP_REQUESTED`、`OLLAMA_TIMEOUT` 还是 `NO_IMPROVEMENT`。
- `score_history.json` 里的 `timeout_this_round`、`invalid_score_this_round`、`repetitive_judge`、`errors`。
- `04_judge.md` 是否是合法 JSON，以及是否给出可信 blockers 和 next_step。

## 7. 可视化有什么用

从研究者视角看，当前 UI 对“运行管理”有用，对“研究质量判断”只提供基础信号。

它能帮助判断 auto research 是否在变好：

- 可以通过 `best_score` 和 `score_history.json` 看分数是否上升。
- 可以查看 `best_output.md` 是否比普通 round 更具体。
- 可以打开每轮 `04_judge.md` 看 judge 的 reasons 和 blockers。

但它还不能充分证明研究真的在变好：

- 分数只来自同一个 judge agent，缺少多 judge、一致性、人工标注或任务级指标。
- `score_history.json` 没保存完整 rubric 子分项趋势。
- 没有自动 diff、novelty drift、重复率、实验可执行度等指标。

它能帮助发现卡顿、重复、退化、跑偏：

- 卡顿：看 `Stage` 和 `run.log` 中 agent start/end 时间。
- 重复：看 `score_history.json` 的 `repetitive_judge`。
- 退化：看分数下降、`non_improve_streak` 增长、best round 长期不更新。
- 跑偏：需要人工打开 `01_draft.md`、`03_revised.md`、`04_judge.md` 判断，目前没有自动主题漂移检测。

它能不能比较两种 drafting mode：

- 目前不能。代码没有显式 `drafting_mode` 配置，也没有把 mode 写入 run metadata。
- 现在只能人工比较不同 run 或不同 round，不能做严格 A/B 实验。

目前还缺的关键指标：

- 每个 agent 的 token 输入/输出、成本、耗时聚合。
- judge rubric 子分项随 round 的趋势。
- draft/revised 与上一轮的相似度、差异摘要、重复率。
- 是否引用了上一轮 draft、上一轮 review、previous best 的可追踪 lineage。
- 不同模型、不同 drafting mode、不同 prompt 版本的 run-level 对比表。
- 可视化曲线：score、耗时、错误、超时、重复、non-improve streak。

## 8. 代码结构导览

主要根目录：

- `README.md`：项目总览、常用命令、UI 说明。
- `docs/USER_GUIDE.md`：已有用户指南。
- `docs/DEVELOPER_GUIDE.md`：已有开发者指南。
- `config.example.yaml`：安全示例配置。
- `config.yaml`：本地主配置，包含模型、Ollama URL、项目名、topic、轮数、停止条件、runtime；不提交。
- `Makefile`：安装、测试、运行、UI 的命令入口。
- `pyproject.toml`：Python 包配置和依赖。
- `requirements.txt`：兼容旧安装方式，指向 `-e .[dev]`。
- `prompts/`：四个 agent 的系统提示词。
- `projects/pama/`：示例 PAMA 项目的输入和模板；运行输出和状态文件不提交。
- `scripts/`：辅助脚本，目前有 import check 和 UI 启动脚本。
- `src/`：核心运行代码。
- `tests/`：单元测试和 smoke test。
- `ui/`：Streamlit UI。

`src/` 主要文件：

- `src/cli.py`：解析 `--diagnostic`、`--continuous`、`--resume`、`--session`、`--model`，分发运行模式。
- `src/main.py`：兼容入口，重新导出旧 API。
- `src/config.py`：加载和校验 `config.yaml`，查询 Ollama 模型，保存默认模型。
- `src/llm.py`：Ollama `/api/chat` 客户端。
- `src/agents.py`：Draft、Review、Revise、Judge agent 封装和 prompt 组装。
- `src/runner.py`：普通/连续/resume 的核心 round loop、停止条件、checkpoint、score history。
- `src/diagnostic.py`：一轮轻量诊断流程，不更新 memory。
- `src/session.py`：session 模式，先生成 objective 和 plan，再跑迭代，最后生成 report。
- `src/resume.py`：读取 checkpoint 并从下一轮继续。
- `src/storage.py`：文件读写、round 输出、score 解析、memory 更新、research_state 更新。
- `src/runtime.py`：后台进程、UI 元数据、run lock、测试运行、停止信号。
- `src/judge_output.py`：judge JSON schema 和分数解析。
- `src/logging_config.py`：结构化日志格式。
- `src/constants.py`：停止原因和运行常量。

后续想改功能应该去哪里：

- 改模型/API 调用：`src/llm.py`、`src/config.py`。
- 改 prompt 内容：`prompts/*.md`。
- 改每轮流程、停止条件、checkpoint：`src/runner.py`。
- 改 draft/review/revise/judge 输入上下文：`src/agents.py` 和 `src/runner.py`。
- 改暂停/继续：`src/runtime.py`、`src/resume.py`、`src/runner.py`。
- 改 UI：`ui/app.py`。
- 改输出结构：`src/storage.py`。
- 加测试：`tests/`。

## 9. 两种 drafting mode 的当前支持情况

目标模式 A：

> 每一轮都基于同一个原始输入重新写 draft，只使用上一轮 review idea 改进。

目标模式 B：

> 每一轮都基于上一轮 draft 继续改写，同时结合上一轮 review idea。

当前是否已实现：

- 没有显式实现 A/B 两种 drafting mode。
- 当前配置 schema 里没有 `drafting_mode`。
- CLI 没有 `--drafting-mode`。
- checkpoint、score_history、run 目录也没有记录 drafting mode。

当前实际行为更像一个混合模式：

- `agents.draft()` 每轮输入包括原始 task、memory、round index、`previous_best`、`previous_judge`。
- `previous_best` 来自当前最佳 `best_output.md`，不是严格的上一轮 draft。
- `previous_judge` 是上一轮 judge，不是上一轮 review。
- `agents.revise()` 只基于同一轮 draft 和同一轮 review 改写。
- memory 会被每轮更新，也会影响下一轮 draft。

所以当前既不是严格 A，也不是严格 B。

最小改法：

- 在配置 schema 加 `drafting_mode`，例如：
  - `fresh_from_task_with_review`
  - `continue_from_previous_draft`
  - 可选第三种保留现状：`best_guided`
- 在 `src/config.py` 增加枚举校验。
- 在 `src/runner.py` 保存 `previous_draft_output`、`previous_review_output`、`previous_revised_output`。
- 在 `src/agents.py` 给 `draft()` 增加明确字段：
  - `drafting_mode`
  - `previous_draft`
  - `previous_review`
  - `previous_revised`
  - `previous_best`
- 调整 draft prompt，让模型知道当前到底应该从原始 task 重新写，还是基于上一轮 draft 续写。
- 把 `drafting_mode` 写入 `checkpoint.json`、`score_history.json`、run-level metadata。
- 为两种模式各加一个 fake-agent 单元测试，验证 prompt 输入和输出落盘行为。

哪个更适合做实验对比：

- A 更适合做严格对照实验，因为每轮都从同一 task 出发，只让 review idea 影响下一轮，比较容易分析“review 是否带来提升”。
- B 更接近真实写作迭代，可能更快收敛，但路径依赖更强，容易累积错误和重复。
- 建议先实现 A/B 显式开关，再用相同模型、相同 task、相同 max_rounds 跑两个 run，比 `score_history`、rubric 子项、重复率、人工可执行度。

## 10. 下一步开发优先级

### 现在立刻做

- 复制 `config.example.yaml` 到本地 `config.yaml`，并按本机模型情况调整模型名。
- 运行 `make check`，把测试恢复到全绿。
- 先不要跑长 continuous；只跑 `make diagnostic ARGS="--model qwen3:8b"` 或 `--model deepseek-r1:8b` 做一轮真实 smoke。
- 打开 UI，确认 `best_output.md`、`checkpoint.json`、`score_history.json` 都能正常浏览。

### 今天可以做

- 给每个 run 增加 `run_config.json`，记录模型、轮数、topic、prompt 文件 hash、drafting mode。
- 把 `score_history.json` 扩展为保留 judge rubric 子分项。
- 在 UI 里加一个简单 score history 表格或折线图。
- 清理 UI 的 Streamlit deprecation warning，把 `use_container_width=True` 改成 `width='stretch'`。
- 明确已有 checkpoint 是否还要继续，还是新开一个 clean run。

### 之后 1-2 天做

- 实现显式 `drafting_mode` A/B 开关。
- 增加两个 run 的比较视图：模型、mode、轮数、最好分、平均分、超时数、重复数。
- 记录每个 agent 的 elapsed seconds 到结构化 JSON，而不是只散落在 log。
- 增加 token 估算或真实 token 统计，为成本/时间分析打基础。
- 让 resume 更清楚地区分“继续旧 run”和“从旧 best 开新 run”。

### 更长期做

- 支持多 provider：本地 Ollama、OpenAI API、其他兼容 API，并统一模型配置。
- 支持完整成本统计：input tokens、output tokens、价格、总成本。
- 支持多 judge 或人工复核，提高分数可信度。
- 支持 prompt 版本管理和 run reproducibility。
- 支持实验 dashboard：score 曲线、rubric 曲线、耗时曲线、重复率、diff、mode 对比。
- 支持导出 research report，把 best output、judge blockers、score trend 汇总成可提交文档。

## 11. 实际建议

第一小时不要急着继续旧 checkpoint。先把项目恢复到“测试全绿 + UI 能看 + 一轮诊断能跑”的状态：创建本地配置，确认模型可用，然后跑 `make check`。接着打开 `best_output.md` 和最近一轮的四个文件，判断高分输出是否真有研究价值。

今晚的目标建议设小一点：跑一个新的 1-round diagnostic，确认输出路径和 UI 都正常；然后实现或至少设计好 `drafting_mode` 的配置字段。不要陷入长时间 continuous，也不要先改大 prompt。这个项目现在最缺的不是更多轮数，而是可比较、可恢复、可解释的实验结构。

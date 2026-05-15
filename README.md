# auto-research-agent

一个本地优先（Ollama）的小型研究循环助手：`Draft -> Review -> Revise -> Judge`。  
适合做学术研究规划草案、迭代改写与快速评分。

详细新手说明请先看：`docs/USER_GUIDE.md`。
开发、测试和架构说明请看：`docs/DEVELOPER_GUIDE.md`。

## 你只需要知道这几件事

- 主要输入文件：`projects/pama/task.md`
- 启动前先做一次快速检查：
  - `make diagnostic`
- 正常有界运行：
  - `make run`
- 推荐默认模型：
  - `qwen3:8b`
- 稳定回退模型：
  - `llama3.1:8b`

## 快速开始

```bash
cd <PROJECT_ROOT>
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

## 输入文件说明

- `projects/pama/task.md`：你的研究任务（必填，最小输入）
- `<PROJECT_MEMORY_FILE>`：历史上下文记忆（可选，程序会自动维护）
- `config.yaml`：运行参数（模型、轮数、超时等）

## 配置安全检查

启动 CLI 或 UI 时会先校验 `config.yaml`。未知字段、错误类型、超出范围的数值、无效
URL 或无效项目名会直接报出具体字段，避免运行到一半才失败。当前推荐格式是嵌套的
`model:` 配置；兼容旧格式 `model: qwen3:8b`，也兼容旧的顶层 `temperature` 和
`timeout_seconds`，但嵌套 `model:` 里的值会优先生效。

`topic:` 配置决定通用提示词收到的项目主题上下文。当前仓库里的 `projects/pama` 是示例
项目；如果换成新研究方向，请新建 `projects/<name>/`，修改 `project_name`，并同步更新
`topic.title`、`topic.description` 和 `topic.keywords`。

## 模型建议（Ollama）

- `qwen3:8b`：推荐默认模型（当前默认值），速度和质量平衡
- `qwen3:14b`：更强但更慢、占用更高
- `deepseek-r1:8b`：推理实验模型（适合对比）
- `llama3.1:8b`：稳定回退模型（fallback，不移除）

模型切换（CLI 覆盖）示例：

```bash
make run ARGS="--model qwen3:8b"
make run ARGS="--model qwen3:14b"
make run ARGS="--model deepseek-r1:8b"
make diagnostic ARGS="--model llama3.1:8b"
```

## 先看哪个输出

先看：`projects/pama/best_output.md`  
再看：`projects/pama/runs/<run_id>/round_xx/` 里的 4 个阶段文件。

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
- 连续运行
  - `make continuous`
- 从检查点恢复
  - `make resume`
- 启动本地图形界面
  - `cd <PROJECT_ROOT> && make ui`
  - 或使用固定路径启动脚本：`<PROJECT_ROOT>/scripts/start_ui.sh`

直接调用入口也可以使用：

```bash
.venv/bin/python -m src.main --diagnostic
.venv/bin/auto-research-agent --diagnostic
```

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
  - `cd <PROJECT_ROOT>`
  - `make ui`
  - 或直接运行：`<PROJECT_ROOT>/scripts/start_ui.sh`
- 路径检查：
  - UI 顶部会显示 `App root`
  - 正确路径应为 `<PROJECT_ROOT>`
- 选择模型：
  - 在 `Model Management` 里从已安装模型下拉框选择（运行按钮会带上 `--model <name>`）
- 拉取模型：
  - 在 `Pull model by name` 输入模型名，点击 `Pull Model`
- 删除模型：
  - 选择已安装模型并勾选确认，点击 `Delete Selected Model`
  - 若该模型正被运行任务使用，UI 会阻止删除
- 输入任务：
  - 在 UI 的 `task.md` 和 `memory.md` 文本框编辑，然后点击 `Save Input`
- 开始运行：
  - `Run Diagnostic` / `Run Normal` / `Run Continuous`
  - UI 会把当前模型自动传给后端（`--model <selected_model>`）
- 运行项目测试：
  - 在 `Project Tests` 里点击 `Run Tests`
  - 会执行当前环境的 `pytest -q`，并在页面显示通过/失败和完整输出
- 安全停止：
  - 点击 `Pause / Stop Safely`（创建 `STOP_REQUESTED`，后端在安全点退出）
- 恢复：
  - 点击 `Resume`（等价 `.venv/bin/python -m src.main --resume`）
- 看结果：
  - 先看 `projects/pama/best_output.md`
  - 再看 `projects/pama/runs/<run_id>/round_xx/`
  - 实时状态看 `projects/pama/checkpoint.json`
  - 实时日志看 `projects/pama/run.log`

推荐模型：

- `qwen3:8b`：默认平衡（推荐先用）
- `qwen3:14b`：效果更强但更慢
- `deepseek-r1:8b`：偏推理实验
- `llama3.1:8b`：稳定回退

模型异常提示：

- 模型未下载：会提示 `Model <name> is not installed. Run: ollama pull <name>`
- Ollama 不可用：会提示 `Ollama is not available ...`

## 关于“连续运行 / 安全停止 / 恢复”

- 连续运行：`make continuous`
- 安全停止：
  - `Ctrl+C`
  - 或创建 `projects/pama/STOP_REQUESTED`（UI 按钮会自动创建）
- 恢复：`make resume`（读取 `projects/pama/checkpoint.json`）
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
- `projects/*/checkpoint.json`
- `projects/*/interrupted_report.md`
- `projects/*/STOP_REQUESTED`
- `.env*`
- `.venv/`

## 推送到 GitHub（稳定版本交接）

```bash
git status
git add .
git commit -m "Add user guide and safe run controls"
git push
```

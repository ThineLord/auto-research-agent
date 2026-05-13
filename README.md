# auto-research-agent

一个本地优先（Ollama）的小型研究循环助手：`Draft -> Review -> Revise -> Judge`。  
适合做学术研究规划草案、迭代改写与快速评分。

详细新手说明请先看：`docs/USER_GUIDE.md`。

## 你只需要知道这几件事

- 主要输入文件：`projects/pama/task.md`
- 启动前先做一次快速检查：
  - `python -m src.main --diagnostic`
- 正常有界运行：
  - `python -m src.main`
- 默认本地模型：
  - `llama3.1:8b`

## 快速开始

```bash
cd auto-research-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.1:8b
python -m src.main --diagnostic
python -m src.main
```

## 输入文件说明

- `projects/pama/task.md`：你的研究任务（必填，最小输入）
- `projects/pama/memory.md`：历史上下文记忆（可选，程序会自动维护）
- `config.yaml`：运行参数（模型、轮数、超时等）

## 先看哪个输出

先看：`projects/pama/best_output.md`  
再看：`projects/pama/runs/<run_id>/round_xx/` 里的 4 个阶段文件。

## 常用命令

- 基础诊断（1 轮、快速验证）
  - `python -m src.main --diagnostic`
- 正常有界运行（按 `max_rounds` 停止）
  - `python -m src.main`
- 会话模式（包含 objective/plan/report）
  - `python -m src.main --session`
- 连续运行
  - `python -m src.main --continuous`
- 从检查点恢复
  - `python -m src.main --resume`
- 启动本地图形界面
  - `streamlit run ui/app.py`

## Graphical UI

- 启动：
  - `streamlit run ui/app.py`
- 输入任务：
  - 在 UI 的 `task.md` 和 `memory.md` 文本框编辑，然后点击 `Save Input`
- 开始运行：
  - `Run Diagnostic` / `Run Normal` / `Run Continuous`
- 安全停止：
  - 点击 `Pause / Stop Safely`（创建 `STOP_REQUESTED`，后端在安全点退出）
- 恢复：
  - 点击 `Resume`（等价 `python -m src.main --resume`）
- 看结果：
  - 先看 `projects/pama/best_output.md`
  - 再看 `projects/pama/runs/<run_id>/round_xx/`
  - 实时状态看 `projects/pama/checkpoint.json`
  - 实时日志看 `projects/pama/run.log`

## 关于“连续运行 / 安全停止 / 恢复”

- 连续运行：`python -m src.main --continuous`
- 安全停止：
  - `Ctrl+C`
  - 或创建 `projects/pama/STOP_REQUESTED`（UI 按钮会自动创建）
- 恢复：`python -m src.main --resume`（读取 `projects/pama/checkpoint.json`）
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

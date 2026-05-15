# USER GUIDE

这份文档面向第一次使用本项目的人，按“输入 -> 运行 -> 看结果 -> 提交 GitHub”来走。

## 这个项目做什么

它会在本地用 Ollama 跑一个研究循环：

1. Draft（起草）
2. Review（审查）
3. Revise（改写）
4. Judge（评分）

每轮都会把中间结果落盘，避免只存在内存中。

## 模型选择建议

- `qwen3:8b`：推荐默认模型（当前默认）
- `qwen3:14b`：更强但更慢，内存占用更高
- `deepseek-r1:8b`：推理实验备选
- `llama3.1:8b`：稳定回退模型（fallback）

命令行切换模型：

```bash
python -m src.main --model qwen3:8b
python -m src.main --model qwen3:14b
python -m src.main --model deepseek-r1:8b
python -m src.main --diagnostic --model llama3.1:8b
```

在 UI 中切换模型：

1. 推荐直接运行：`<PROJECT_ROOT>/scripts/start_ui.sh`
2. 或手动进入唯一项目目录：`cd <PROJECT_ROOT>`
3. 启动虚拟环境：`source .venv/bin/activate`
4. 打开 `streamlit run ui/app.py`
5. 确认 UI 顶部的 `App root` 是 `<PROJECT_ROOT>`
6. 在 `Model Management` 的下拉框选已安装模型
7. 点击 `Run Diagnostic / Run Normal / Run Continuous / Resume`
8. UI 会自动传参：`--model <selected_model>`

在 UI 中拉取模型：

1. 在 `Pull model by name` 输入模型名
2. 点击 `Pull Model`
3. 在 `Model operation logs` 查看拉取进度

在 UI 中删除模型：

1. 在删除下拉框选已安装模型
2. 勾选确认框
3. 点击 `Delete Selected Model`
4. 若模型正在被当前运行使用，UI 会阻止删除

常见模型相关错误：

- 未安装模型：
  - `Model <name> is not installed. Run: ollama pull <name>`
- Ollama 未运行或不可用：
  - `Ollama is not available ...`

模型检查命令：

```bash
ollama list
ollama run qwen3:8b
```

## 我该把输入写在哪里

核心输入写在：`projects/pama/task.md`

可选补充写在：`<PROJECT_MEMORY_FILE>`

- `task.md`：你本次希望研究/回答的问题（必须有内容）
- `memory.md`：历史上下文、限制、已知结论（可空，程序会自动更新）

## 最小输入需要什么

最小只需要：

- `projects/pama/task.md` 里有清晰问题描述

其他都可以保持默认。

## 我应该先跑哪个命令

先跑诊断：

```bash
python -m src.main --diagnostic
```

确认本机模型、提示词和文件写入都正常，再跑正式模式。

## 连续运行用哪个命令

```bash
python -m src.main --continuous
```

连续模式会逐轮执行，并在每轮持续写入输出和检查点。

## 如何安全停止

有两种方式：

1. 终端按 `Ctrl+C`
2. 在 Streamlit UI 里点击 `Pause / Stop Safely`（会创建 `STOP_REQUESTED`）

程序会在安全点停止，并生成：

- `projects/pama/checkpoint.json`
- `projects/pama/interrupted_report.md`

## 如何恢复（resume）

```bash
python -m src.main --resume
```

恢复会读取 `projects/pama/checkpoint.json`：

- 从 `last_completed_round + 1` 继续
- 不覆盖已有 round 文件
- 只有更高分时才更新 `best_output.md`

## 输出文件怎么读（先看哪个）

先看：`projects/pama/best_output.md`

这是当前最佳版本（按 Judge 分数）。

再看：`projects/pama/runs/<run_id>/round_xx/`

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
- `.env*`
- `.venv/`

## 推送当前稳定状态到 GitHub

```bash
git status
git add .
git commit -m "Stabilize runtime and improve user documentation"
git push
```

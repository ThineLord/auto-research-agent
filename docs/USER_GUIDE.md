# USER GUIDE

这份文档面向第一次使用本项目的人，按“输入 -> 运行 -> 看结果 -> 提交 GitHub”来走。

## 这个项目做什么

它会在本地用 Ollama 跑一个研究循环：

1. Draft（起草）
2. Review（审查）
3. Revise（改写）
4. Judge（评分）

每轮都会把中间结果落盘，避免只存在内存中。

## 我该把输入写在哪里

核心输入写在：`projects/pama/task.md`

可选补充写在：`projects/pama/memory.md`

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

当前稳定版本未提供 `--continuous`。  
建议用有界模式多次运行：

```bash
python -m src.main
```

它会按 `config.yaml` 的 `max_rounds` 自动停止。

## 如何安全停止

直接 `Ctrl+C`。  
由于每轮都会立即写入 `runs/round_xx`，已完成轮次不会丢失。

## 如何恢复（resume）

当前稳定版本未提供 `--resume`。  
建议恢复方式：

1. 保留已有 `projects/pama/memory.md`
2. 再次执行 `python -m src.main`

程序会基于当前 `task.md + memory.md` 继续推进。

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

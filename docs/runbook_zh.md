# Auto Research Agent 安全实验 Runbook

目标：今天安全跑一个小实验，能看到输出、打开 UI、理解结果，并且不覆盖已有 runs。

## 1. 先确认环境

```bash
cd auto-research-agent
cp config.example.yaml config.yaml
source .venv/bin/activate
```

进入项目、创建本地配置并激活虚拟环境。

```bash
make lint
make format-check
make import-check
.venv/bin/python -m pytest -q
```

先跑本地检查。当前期望结果：全部通过。

```bash
ollama list
```

确认 Ollama 可用，并确认你想用的本地模型已经安装。若只跑 Gemini 模式，改为确认
`GEMINI_API_KEY` 或 `GOOGLE_API_KEY` 已设置；若只跑 `make survey`，不需要 Ollama 或 Gemini。

## 2. 如何跑 fake/mock 模式

当前项目没有正式 CLI mock 参数，例如没有：

```bash
python -m src.main --mock
```

现有 fake/mock 覆盖在测试里，适合验证“循环能写文件、best score 能更新、UI helper 能读状态”，不会调用 Ollama：

```bash
.venv/bin/python -m pytest tests/test_round_loop.py::RoundLoopTests::test_round_loop_writes_outputs_and_keeps_best_score -q
```

验证 round loop 用 fake agents 落盘。

```bash
.venv/bin/python -m pytest tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_progress_resume_and_output_helpers -q
```

验证 UI progress/resume/output catalog helper。

如果之后要加真正 mock run，最小方向是在 `src/cli.py` 增加 `--mock`，在 `src/runner.py` 复用现有 round loop，注入 fake `ResearchAgents`。

## 3. 如何跑一次最小真实模型模式

最安全的一轮真实实验是 diagnostic：

```bash
make diagnostic ARGS="--model qwen3:8b"
```

或使用本地配置里的默认模型：

```bash
make diagnostic
```

Diagnostic 的特点：

- 固定 1 轮。
- 会调用 Ollama。
- 会生成新的 `projects/example/runs/<run_id>/round_01/`。
- 会写 `projects/example/runs/<run_id>/run_config.json`。
- 会写 `projects/example/checkpoint.json` 和 `projects/example/score_history.json`。
- 不更新 `memory.md`，比较适合 smoke test。

如果你想明确指定另一个已安装模型，例如 `deepseek-r1:8b`：

```bash
make diagnostic ARGS="--model deepseek-r1:8b"
```

如果要跑 Gemini 诊断：

```bash
make diagnostic ARGS="--provider gemini --model gemini-3.5-flash"
```

这需要有效的 Gemini API key。云端模式不会检查本机 Ollama 模型。

## 4. 如何避免长时间运行

优先用：

```bash
make diagnostic ARGS="--model qwen3:8b"
```

避免在今天的 smoke test 里直接用：

```bash
make continuous
make session
make resume
```

原因：

- `continuous` 设计上会持续跑。
- `session` 会先生成 objective/plan，再跑迭代，再生成 report，调用次数更多。
- `resume` 会从本地 `projects/example/checkpoint.json` 继续旧 run，并在启动前显示 resume
  preview；它不是新建 run 后使用 `best_output.md` 作为 previous-best context。

如果误启动了长任务：

```bash
touch projects/example/STOP_REQUESTED
```

请求安全停止。程序会在安全点退出，并更新 checkpoint。

终端里直接运行的进程，也可以按：

```bash
Ctrl+C
```

## 5. 如何指定 rounds 数量

默认 rounds 来自 `config.yaml`：

```yaml
max_rounds: 5
```

要跑 1 轮，不要改配置，直接用 diagnostic。

要跑 2 轮普通模式，可以直接用 CLI override：

```bash
make run ARGS="--model qwen3:8b --max-rounds 2"
```

如果希望长期改变默认轮数，再修改本地 `config.yaml`；该文件不提交。

## 5.1 如何指定 drafting mode

默认 `drafting_mode` 是 `best_guided`，保持旧行为。临时对比其他模式：

```bash
make run ARGS="--drafting-mode fresh_from_task_with_review --max-rounds 2"
make run ARGS="--drafting-mode continue_from_previous_draft --max-rounds 2"
```

UI 的 `C. Run controls` 里也可以选择起草模式。每次运行会把 `drafting_mode` 写入
`checkpoint.json`、`score_history.json` 和 `runs/<run_id>/run_config.json`。

## 6. 如何指定模型

CLI 支持 `--model` 覆盖配置：

```bash
make diagnostic ARGS="--model qwen3:8b"
make run ARGS="--model deepseek-r1:8b"
make resume ARGS="--model llama3.1:8b"
```

如果模型没安装，会提示：

```text
Model <name> is not installed. Run: ollama pull <name>
```

拉取模型：

```bash
ollama pull qwen3:8b
```

## 7. 如何查看输出目录

如果只想整理项目里的论文和相关工作，不调用模型：

```bash
make survey
```

Survey 输出默认写到 `projects/<project>/survey/`，包括 `survey_report.md`、`paper_metadata.json`、
`related_work.md` 和 `survey_manifest.json`。
JSON 输出会记录 DOI/arXiv 规范化后的去重结果，以及缺失作者、年份、venue、URL/DOI/arXiv 的质量计数。

最新 checkpoint：

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
checkpoint = json.loads(Path("projects/example/checkpoint.json").read_text())
print("run_root:", checkpoint.get("run_root"))
print("last_completed_round:", checkpoint.get("last_completed_round"))
print("best_score:", checkpoint.get("best_score"))
print("stop_reason:", checkpoint.get("stop_reason"))
print("run_config:", checkpoint.get("run_config"))
print("run_summary:", checkpoint.get("run_summary"))
PY
```

列出最近 run：

```bash
ls -lt projects/example/runs | head
```

查看某一轮四个文件：

```bash
ls projects/example/runs/<run_id>/round_01
```

通常会看到：

```text
01_draft.md
02_review.md
03_revised.md
04_judge.md
```

复现实验设置：

```bash
sed -n '1,220p' projects/example/runs/<run_id>/run_config.json
sed -n '1,220p' projects/example/runs/<run_id>/run_summary.json
```

对比两个或多个 run：

```bash
.venv/bin/python -m src.main --compare-runs projects/example/runs/<run_a> projects/example/runs/<run_b>
```

优先阅读：

```bash
sed -n '1,220p' projects/example/best_output.md
```

再看最新 round：

```bash
sed -n '1,220p' projects/example/runs/<run_id>/round_01/04_judge.md
sed -n '1,220p' projects/example/runs/<run_id>/round_01/03_revised.md
```

## 8. 如何用 Streamlit 打开 UI

```bash
make ui
```

打开：

```text
http://localhost:8501
```

备用脚本：

```bash
scripts/start_ui.sh
```

UI 中重点看：

- `A. Project selector`：默认应为公开安全的 `example`；如需运行自己的项目，再手动选择。
- `C. Run controls`：启动 diagnostic/normal/continuous/resume，或安全暂停。
- `D. Progress panel`：看 Mode、Round、Stage、Best score、Model、Stop reason。
- `E. Live logs panel`：看 `run.log` 和模型操作日志。
- `Latest run metadata`：看 provider/model、drafting mode、Git commit、stop reason、best score。
- `Run comparison`：选择多个 run，对比模型、起草模式、轮数、best/average score、timeout/error counts、agent 总耗时和估算 token。
- `F. Output browser`：看 best output、checkpoint、run config、run summary、round metrics、score history、latest round draft/review/revised/judge。

## 9. 如何停止 UI

如果 UI 是前台运行：

```bash
Ctrl+C
```

确认端口已释放：

```bash
lsof -iTCP:8501 -sTCP:LISTEN -n -P || true
```

没有输出表示 8501 没有服务在监听。

## 10. 如何判断这次 run 是否成功

一个最小真实 run 成功，至少满足：

- 终端没有报 `Config error`、`Model ... is not installed`、`Ollama is not available`。
- `projects/example/checkpoint.json` 存在且 `last_completed_round >= 1`。
- `projects/example/checkpoint.json` 里 `run_root` 指向的目录存在。
- `projects/example/checkpoint.json` 里 `run_config` 指向的 `run_config.json` 存在。
- `checkpoint.json` / `run_config.json` / `run_summary.json` 里有 `resume_metadata`，能区分
  `resume_existing_run` 和 `start_new_run`。
- `run_root/run_summary.json` 和 `run_root/round_metrics.json` 存在。
- `run_summary.json` 里有 `total_elapsed_seconds`、`total_agent_elapsed_seconds`、
  `total_estimated_tokens`、`timeout_count` 和 `error_count`；这些 token 是字符数估算，不是账单 token。
- `run_root/round_01/01_draft.md`、`02_review.md`、`03_revised.md`、`04_judge.md` 都存在。
- `projects/example/score_history.json` 有至少一条记录。
- `04_judge.md` 能解析出分数，或 `score_history.json` 里 `invalid_score_this_round` 是 `false`。

快速检查：

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
project = Path("projects/example")
checkpoint = json.loads((project / "checkpoint.json").read_text())
run_root = Path(checkpoint["run_root"])
round_dir = run_root / f"round_{int(checkpoint['last_completed_round']):02d}"
files = ["01_draft.md", "02_review.md", "03_revised.md", "04_judge.md"]
print("run_root:", run_root)
print("round_dir:", round_dir)
print("stop_reason:", checkpoint.get("stop_reason"))
print("best_score:", checkpoint.get("best_score"))
run_config = Path(checkpoint.get("run_config") or run_root / "run_config.json")
run_summary = Path(checkpoint.get("run_summary") or run_root / "run_summary.json")
round_metrics = run_root / "round_metrics.json"
print("run_config:", "OK" if run_config.exists() else "MISSING")
print("run_summary:", "OK" if run_summary.exists() else "MISSING")
print("round_metrics:", "OK" if round_metrics.exists() else "MISSING")
for name in files:
    path = round_dir / name
    print(name, "OK" if path.exists() and path.stat().st_size > 0 else "MISSING/EMPTY")
PY
```

如果 `stop_reason` 是 `OLLAMA_TIMEOUT`，说明模型调用太慢或超时；下次优先换更小模型，或只跑 diagnostic。

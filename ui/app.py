from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

import requests
import streamlit as st

from src.config import (
    ConfigValidationError,
    load_app_config,
    query_ollama_models,
    save_default_model_name,
)
from src.runtime import (
    get_active_process_meta,
    model_job_meta_path,
    run_meta_path,
    run_project_tests,
    start_background_process,
)
from src.storage import read_file_text, read_json_file, tail_file_lines, write_file_text

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"
CONFIG_PATH = ROOT / "config.yaml"
CANONICAL_ROOT = Path(
    os.environ.get(
        "AUTO_RESEARCH_AGENT_ROOT",
        str(ROOT),
    )
).resolve()

AGENT_LOG_RE = re.compile(
    r"round=(?P<round>\d+)\s+\|\s+agent=(?P<agent>\w+)\s+\|\s+status=(?P<status>\w+)"
)
ROUND_ENTER_RE = re.compile(r"round_enter round=(?P<round>\d+)")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def check_model_health(
    *,
    base_url: str,
    selected_model: str,
    installed_model_names: Sequence[str],
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    model_name = selected_model.strip()
    if not model_name:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": "No model selected.",
        }

    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Ollama API timed out at {base_url}.",
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Ollama API is not healthy at {base_url}: {exc}",
        }

    api_models = [
        str(model.get("name", "")).strip()
        for model in payload.get("models", [])
        if isinstance(model, dict)
    ]
    available_models = {name for name in installed_model_names if name} | {
        name for name in api_models if name
    }
    model_ok = model_name in available_models
    if not model_ok:
        return {
            "ok": False,
            "api_ok": True,
            "model_ok": False,
            "message": f"Ollama is reachable, but `{model_name}` is not installed.",
        }
    return {
        "ok": True,
        "api_ok": True,
        "model_ok": True,
        "message": f"Ollama is reachable and `{model_name}` is installed.",
    }


def infer_running_stage(
    *,
    log_text: str,
    checkpoint: dict[str, Any],
    run_meta: dict[str, Any],
) -> dict[str, Any]:
    run_active = bool(run_meta)
    latest_round = _safe_int(checkpoint.get("last_completed_round"))
    stage = "Idle"
    stage_status = "idle"

    for line in reversed(log_text.splitlines()):
        agent_match = AGENT_LOG_RE.search(line)
        if agent_match:
            latest_round = _safe_int(agent_match.group("round"), latest_round)
            agent = agent_match.group("agent")
            status = agent_match.group("status")
            if status == "start":
                stage = agent
                stage_status = "running"
            elif run_active:
                stage = f"after {agent}"
                stage_status = status
            else:
                stage = "Idle"
                stage_status = status
            break
        round_match = ROUND_ENTER_RE.search(line)
        if round_match:
            latest_round = _safe_int(round_match.group("round"), latest_round)
            if run_active:
                stage = "starting round"
                stage_status = "running"
            break

    if run_active and stage == "Idle":
        stage = "starting"
        stage_status = "running"

    return {
        "run_active": run_active,
        "pid": run_meta.get("pid", "N/A") if run_active else "N/A",
        "mode": run_meta.get("mode") or checkpoint.get("mode", "N/A"),
        "model": run_meta.get("model") or checkpoint.get("model", "N/A"),
        "round": latest_round or "N/A",
        "stage": stage,
        "stage_status": stage_status,
        "last_successful_agent": checkpoint.get("last_successful_agent", "N/A"),
        "best_score": checkpoint.get("best_score", "N/A"),
        "stop_reason": checkpoint.get("stop_reason", "N/A"),
        "can_resume": bool(checkpoint.get("can_resume", False)),
    }


def describe_resume_state(
    *,
    checkpoint: dict[str, Any],
    run_active: bool,
    selected_model: str,
) -> dict[str, Any]:
    if not checkpoint:
        return {
            "can_resume": False,
            "level": "info",
            "message": "No checkpoint exists yet. Run a workflow before resuming.",
        }
    if run_active:
        return {
            "can_resume": False,
            "level": "warning",
            "message": "A run is active. Resume is blocked until the current run exits.",
        }

    checkpoint_model = str(checkpoint.get("model", "")).strip()
    selected_model = selected_model.strip()
    model_note = ""
    if checkpoint_model and selected_model and checkpoint_model != selected_model:
        model_note = (
            f" Checkpoint model was `{checkpoint_model}`; selected model is `{selected_model}`."
        )

    if checkpoint.get("can_resume"):
        next_round = _safe_int(checkpoint.get("last_completed_round")) + 1
        return {
            "can_resume": True,
            "level": "success",
            "message": f"Resume available from round {next_round}.{model_note}",
        }

    stop_reason = checkpoint.get("stop_reason", "unknown")
    return {
        "can_resume": False,
        "level": "info",
        "message": f"Resume is unavailable. Last stop reason: `{stop_reason}`.{model_note}",
    }


def detect_output_kind(path: Path) -> str:
    if path.suffix == ".json":
        return "json"
    if path.suffix == ".log":
        return "log"
    if path.suffix in {".md", ".markdown"}:
        return "markdown"
    return "text"


def build_output_catalog(project_dir: Path, checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = [
        {"label": "Best output", "path": project_dir / "best_output.md"},
        {"label": "Final session report", "path": project_dir / "final_session_report.md"},
        {"label": "Interrupted report", "path": project_dir / "interrupted_report.md"},
        {"label": "Checkpoint", "path": project_dir / "checkpoint.json"},
        {"label": "Score history", "path": project_dir / "score_history.json"},
        {"label": "Run log", "path": project_dir / "run.log"},
        {"label": "Model operation log", "path": project_dir / "model_ops.log"},
    ]

    run_root = Path(str(checkpoint.get("run_root", "")))
    round_index = _safe_int(checkpoint.get("last_completed_round"))
    if round_index > 0 and run_root.exists():
        round_dir = run_root / f"round_{round_index:02d}"
        catalog.extend(
            [
                {"label": "Latest round draft", "path": round_dir / "01_draft.md"},
                {"label": "Latest round review", "path": round_dir / "02_review.md"},
                {"label": "Latest round revised", "path": round_dir / "03_revised.md"},
                {"label": "Latest round judge", "path": round_dir / "04_judge.md"},
            ]
        )

    return [
        {
            "label": item["label"],
            "path": item["path"],
            "kind": detect_output_kind(item["path"]),
            "exists": item["path"].exists(),
        }
        for item in catalog
    ]


def live_refresh_interval(auto_refresh: bool) -> str | None:
    return "2s" if auto_refresh else None


def project_path(project_name: str) -> Path:
    return PROJECTS_DIR / project_name


def is_canonical_root() -> bool:
    return ROOT.resolve() == CANONICAL_ROOT


def render_runtime_location_check() -> None:
    st.caption(f"App root: `{ROOT}`")
    if is_canonical_root():
        st.success("Running from the canonical project folder.")
        return

    st.error(
        "This Streamlit app is not running from the canonical project folder. "
        "Stop this server and restart Streamlit from the path below."
    )
    st.code(
        f"cd {CANONICAL_ROOT}\nmake ui",
        language="bash",
    )


def render_process_result(result, success_message: str) -> None:
    if result.error:
        st.error(result.error)
    elif result.pid:
        st.success(success_message.format(pid=result.pid))


def render_live_progress_and_logs(
    *,
    proj_path: Path,
    run_log_path: Path,
    model_job_log_path: Path,
    checkpoint_path: Path,
    stop_signal_path: Path,
    default_model: str,
) -> None:
    run_meta = get_active_process_meta(run_meta_path(proj_path))
    checkpoint = read_json_file(checkpoint_path) if checkpoint_path.exists() else {}
    run_log_text = tail_file_lines(run_log_path, max_lines=240)

    progress = infer_running_stage(
        log_text=run_log_text,
        checkpoint=checkpoint,
        run_meta=run_meta,
    )
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Mode", str(progress["mode"]))
    p2.metric("Round", str(progress["round"]))
    p3.metric("Stage", str(progress["stage"]))
    p4.metric("Best score", str(progress["best_score"]))
    st.write(f"PID: `{progress['pid']}`")
    st.write(f"Model: `{progress['model']}`")
    st.write(f"Last successful agent: `{progress['last_successful_agent']}`")
    st.write(f"Stop reason: `{progress['stop_reason']}`")
    st.write(f"Stop signal present: `{stop_signal_path.exists()}`")
    st.write(f"Selected model: `{st.session_state.get('selected_model', default_model)}`")

    st.subheader("E. Live logs panel")
    st.code(run_log_text or "(no logs yet)", language="text")
    st.caption("Model operation logs")
    st.code(
        tail_file_lines(model_job_log_path, max_lines=120) or "(no model operation logs yet)",
        language="text",
    )


def main() -> None:
    st.set_page_config(page_title="Auto Research Agent", layout="wide")
    st.title("Auto Research Agent")
    render_runtime_location_check()
    try:
        app_config = load_app_config(CONFIG_PATH)
    except (ConfigValidationError, FileNotFoundError) as exc:
        st.error(f"Config error: {exc}")
        st.stop()

    st.subheader("Quick Actions")
    quick_test_col, quick_status_col = st.columns([1, 3])
    with quick_test_col:
        if st.button("Run Tests", key="run_tests_quick"):
            st.session_state["test_result"] = run_project_tests(ROOT)
    with quick_status_col:
        quick_test_result = st.session_state.get("test_result")
        if quick_test_result:
            if quick_test_result["ok"]:
                st.success(f"Tests passed in {quick_test_result['elapsed']:.2f}s")
            else:
                st.error(f"Tests failed in {quick_test_result['elapsed']:.2f}s")
        else:
            st.info("Click Run Tests to check the project without running Ollama.")

    projects = (
        sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()])
        if PROJECTS_DIR.exists()
        else []
    )
    default_index = (
        projects.index(app_config.project_name) if app_config.project_name in projects else 0
    )
    selected_project = st.selectbox(
        "A. Project selector", projects, index=default_index if projects else None
    )
    if not selected_project:
        st.warning("No project found under projects/.")
        return

    proj_path = project_path(selected_project)
    st.write(f"Project path: `{proj_path}`")

    task_path = proj_path / "task.md"
    memory_path = proj_path / "memory.md"
    run_log_path = proj_path / "run.log"
    model_job_log_path = proj_path / "model_ops.log"
    checkpoint_path = proj_path / "checkpoint.json"
    stop_signal_path = proj_path / "STOP_REQUESTED"
    run_meta = get_active_process_meta(run_meta_path(proj_path))
    model_job_meta = get_active_process_meta(model_job_meta_path(proj_path))
    checkpoint = read_json_file(checkpoint_path) if checkpoint_path.exists() else {}

    col_input_left, col_input_right = st.columns(2)
    with col_input_left:
        task_text = st.text_area(
            "B. Input editor - task.md", value=read_file_text(task_path), height=260
        )
    with col_input_right:
        memory_text = st.text_area(
            "B. Input editor - memory.md", value=read_file_text(memory_path), height=260
        )
    if st.button("Save Input"):
        write_file_text(task_path, task_text)
        write_file_text(memory_path, memory_text)
        st.success("task.md and memory.md saved.")

    st.subheader("C. Run controls")
    run_active = bool(run_meta)
    model_job_active = bool(model_job_meta)
    blocked = run_active or model_job_active
    if run_active:
        st.info(f"Run active (PID {run_meta.get('pid')}): `{run_meta.get('command')}`")
    if model_job_active:
        st.warning(
            f"Model job active (PID {model_job_meta.get('pid')}): `{model_job_meta.get('command')}`"
        )

    models, models_error = query_ollama_models(timeout_seconds=15)
    installed_model_names = [m["name"] for m in models]
    default_model = app_config.model.name
    if "selected_model" not in st.session_state:
        st.session_state["selected_model"] = default_model
    if st.session_state["selected_model"] not in installed_model_names and installed_model_names:
        st.session_state["selected_model"] = installed_model_names[0]

    if models_error:
        st.error(models_error)
    st.write(f"Selected model: `{st.session_state.get('selected_model', default_model)}`")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        if st.button("Run Diagnostic", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            result = start_background_process(
                command=[sys.executable, "-m", "src.main", "--diagnostic", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model, "mode": "diagnostic"},
            )
            render_process_result(
                result,
                f"Started diagnostic run with model `{model}` (PID {{pid}})",
            )
    with c2:
        if st.button("Run Normal", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            result = start_background_process(
                command=[sys.executable, "-m", "src.main", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model, "mode": "normal"},
            )
            render_process_result(
                result,
                f"Started normal run with model `{model}` (PID {{pid}})",
            )
    with c3:
        if st.button("Run Continuous", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            result = start_background_process(
                command=[sys.executable, "-m", "src.main", "--continuous", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model, "mode": "continuous"},
            )
            render_process_result(
                result,
                f"Started continuous run with model `{model}` (PID {{pid}})",
            )
    with c4:
        if st.button("Pause / Stop Safely", disabled=not run_active):
            write_file_text(stop_signal_path, "STOP_REQUESTED\n")
            st.warning(f"Stop signal created: `{stop_signal_path}`")
    resume_state = describe_resume_state(
        checkpoint=checkpoint,
        run_active=run_active,
        selected_model=st.session_state.get("selected_model", default_model),
    )
    with c5:
        if st.button(
            "Resume",
            disabled=blocked or bool(models_error) or not resume_state["can_resume"],
        ):
            model = st.session_state.get("selected_model", default_model)
            result = start_background_process(
                command=[sys.executable, "-m", "src.main", "--resume", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model, "mode": "resume"},
            )
            render_process_result(
                result,
                f"Started resume run with model `{model}` (PID {{pid}})",
            )
    with c6:
        if st.button("Run Tests", disabled=run_active, key="run_tests_top"):
            st.session_state["test_result"] = run_project_tests(ROOT)

    if resume_state["level"] == "success":
        st.success(resume_state["message"])
    elif resume_state["level"] == "warning":
        st.warning(resume_state["message"])
    else:
        st.info(resume_state["message"])

    st.subheader("Project Tests")
    st.caption("Run the local automated tests without starting Ollama.")
    test_col_left, test_col_right = st.columns([1, 3])
    with test_col_left:
        if st.button("Run Tests", disabled=run_active, key="run_tests_panel"):
            st.session_state["test_result"] = run_project_tests(ROOT)
    with test_col_right:
        last_test = st.session_state.get("test_result")
        if last_test:
            if last_test["ok"]:
                st.success(
                    f"Tests passed in {last_test['elapsed']:.2f}s using `{last_test['command']}`"
                )
            else:
                returncode = last_test["returncode"]
                st.error(f"Tests failed in {last_test['elapsed']:.2f}s (return code: {returncode})")
        else:
            st.info("No test run yet.")
    if st.session_state.get("test_result"):
        with st.expander("Test output", expanded=True):
            st.code(st.session_state["test_result"]["output"], language="text")

    st.subheader("Model Management")
    st.caption("Available to download: any valid Ollama model name.")
    rec = {
        "qwen3:8b": "default balanced model",
        "qwen3:14b": "stronger, slower",
        "deepseek-r1:8b": "reasoning-oriented experiment",
        "llama3.1:8b": "stable fallback",
    }
    st.markdown("**Recommended models**")
    for name, desc in rec.items():
        installed_tag = " (installed)" if name in installed_model_names else ""
        st.write(f"- `{name}` — {desc}{installed_tag}")

    st.markdown("**Installed models**")
    if models:
        st.dataframe(
            [{"name": m["name"], "size": m["size"], "modified": m["modified"]} for m in models],
            use_container_width=True,
        )
    else:
        st.caption("No installed model found.")

    if installed_model_names:
        selected_model = st.selectbox(
            "Model selector",
            installed_model_names,
            index=installed_model_names.index(st.session_state["selected_model"])
            if st.session_state["selected_model"] in installed_model_names
            else 0,
        )
        st.session_state["selected_model"] = selected_model
    else:
        selected_model = st.text_input(
            "Model selector (manual)", value=st.session_state["selected_model"]
        )
        st.session_state["selected_model"] = selected_model.strip()

    health_col, health_result_col = st.columns([1, 3])
    with health_col:
        if st.button("Check Model Health"):
            st.session_state["model_health"] = check_model_health(
                base_url=app_config.ollama_base_url,
                selected_model=st.session_state.get("selected_model", ""),
                installed_model_names=installed_model_names,
            )
    with health_result_col:
        model_health = st.session_state.get("model_health")
        if model_health:
            if model_health["ok"]:
                st.success(model_health["message"])
            else:
                st.error(model_health["message"])
        else:
            st.info("Run a fast health check before starting long workflows.")

    if st.button("Save Selected Model as Default", disabled=bool(models_error)):
        model_to_save = st.session_state.get("selected_model", "").strip()
        if not model_to_save:
            st.error("Model name is empty.")
        else:
            err = save_default_model_name(CONFIG_PATH, model_to_save)
            if err:
                st.error(err)
            else:
                st.success(f"Saved `{model_to_save}` to config.yaml (model.name).")

    pull_model_name = st.text_input("Pull model by name", value="qwen3:8b")
    if st.button("Pull Model", disabled=blocked):
        pull_model_name = pull_model_name.strip()
        if not pull_model_name:
            st.error("Please enter a model name.")
        else:
            result = start_background_process(
                command=["ollama", "pull", pull_model_name],
                cwd=ROOT,
                log_path=model_job_log_path,
                meta_path=model_job_meta_path(proj_path),
                kind="model_pull",
                extra={"model": pull_model_name},
            )
            render_process_result(
                result,
                f"Started pulling model `{pull_model_name}` (PID {{pid}})",
            )

    delete_target = st.selectbox(
        "Delete model (installed)",
        installed_model_names if installed_model_names else ["(none)"],
    )
    confirm_delete = st.checkbox("I understand deletion cannot be undone.")
    if st.button("Delete Selected Model", disabled=blocked or not installed_model_names):
        if not confirm_delete:
            st.error("Please confirm deletion first.")
        elif run_active and delete_target == str(run_meta.get("model", "")):
            st.error("Cannot delete the model used by the currently running task.")
        elif delete_target == "(none)":
            st.error("No deletable model selected.")
        else:
            result = start_background_process(
                command=["ollama", "rm", delete_target],
                cwd=ROOT,
                log_path=model_job_log_path,
                meta_path=model_job_meta_path(proj_path),
                kind="model_delete",
                extra={"model": delete_target},
            )
            render_process_result(
                result,
                f"Started deleting model `{delete_target}` (PID {{pid}})",
            )

    st.subheader("D. Progress panel")
    auto_refresh = st.checkbox(
        "Auto refresh logs every 2 seconds",
        value=True,
        key="auto_refresh_logs",
    )
    live_panel = st.fragment(run_every=live_refresh_interval(auto_refresh))(
        render_live_progress_and_logs
    )
    live_panel(
        proj_path=proj_path,
        run_log_path=run_log_path,
        model_job_log_path=model_job_log_path,
        checkpoint_path=checkpoint_path,
        stop_signal_path=stop_signal_path,
        default_model=default_model,
    )

    st.subheader("F. Output browser")
    output_catalog = build_output_catalog(proj_path, checkpoint)
    selected_output_index = st.selectbox(
        "Output file",
        range(len(output_catalog)),
        format_func=lambda idx: (
            output_catalog[idx]["label"]
            if output_catalog[idx]["exists"]
            else f"{output_catalog[idx]['label']} (not generated)"
        ),
    )
    selected_output = output_catalog[selected_output_index]
    selected_path = selected_output["path"]
    st.caption(str(selected_path))
    if not selected_output["exists"]:
        st.info("This output has not been generated yet.")
    else:
        content = read_file_text(selected_path)
        if selected_output["kind"] == "json":
            try:
                st.json(json.loads(content))
            except json.JSONDecodeError:
                st.code(content, language="text")
        elif selected_output["kind"] == "markdown":
            st.markdown(content or "_Empty file._")
        else:
            st.code(content or "(empty file)", language="text")


if __name__ == "__main__":
    main()

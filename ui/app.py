from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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
        str(Path.home() / "GitHub_Repository" / "auto-research-agent"),
    )
).resolve()


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
    default_index = projects.index("pama") if "pama" in projects else 0
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
                extra={"model": model},
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
                extra={"model": model},
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
                extra={"model": model},
            )
            render_process_result(
                result,
                f"Started continuous run with model `{model}` (PID {{pid}})",
            )
    with c4:
        if st.button("Pause / Stop Safely", disabled=not run_active):
            write_file_text(stop_signal_path, "STOP_REQUESTED\n")
            st.warning(f"Stop signal created: `{stop_signal_path}`")
    with c5:
        if st.button("Resume", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            result = start_background_process(
                command=[sys.executable, "-m", "src.main", "--resume", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model},
            )
            render_process_result(
                result,
                f"Started resume run with model `{model}` (PID {{pid}})",
            )
    with c6:
        if st.button("Run Tests", disabled=run_active, key="run_tests_top"):
            st.session_state["test_result"] = run_project_tests(ROOT)

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
    checkpoint = {}
    if checkpoint_path.exists():
        checkpoint = read_json_file(checkpoint_path)
    st.write(f"current mode: `{checkpoint.get('mode', 'N/A')}`")
    st.write(f"current round: `{checkpoint.get('last_completed_round', 'N/A')}`")
    st.write(f"current agent: `{checkpoint.get('last_successful_agent', 'N/A')}`")
    st.write(f"last successful agent: `{checkpoint.get('last_successful_agent', 'N/A')}`")
    st.write(f"best score: `{checkpoint.get('best_score', 'N/A')}`")
    st.write(f"stop reason: `{checkpoint.get('stop_reason', 'N/A')}`")
    st.write(f"can resume: `{checkpoint.get('can_resume', False)}`")
    st.write(f"stop signal present: `{stop_signal_path.exists()}`")
    st.write(f"selected model: `{st.session_state.get('selected_model', default_model)}`")

    st.subheader("E. Live logs panel")
    auto_refresh = st.checkbox("Auto refresh logs every 2 seconds", value=True)
    st.code(tail_file_lines(run_log_path, max_lines=240) or "(no logs yet)", language="text")
    st.caption("Model operation logs")
    st.code(
        tail_file_lines(model_job_log_path, max_lines=120) or "(no model operation logs yet)",
        language="text",
    )
    if auto_refresh:
        components.html(
            "<script>setTimeout(function(){window.location.reload();}, 2000);</script>",
            height=0,
        )

    st.subheader("F. Output panel")
    output_files = [
        proj_path / "best_output.md",
        proj_path / "final_session_report.md",
        proj_path / "interrupted_report.md",
        proj_path / "checkpoint.json",
        proj_path / "score_history.json",
    ]
    for output in output_files:
        st.write(f"- `{output}`")
        if output.exists():
            preview = read_file_text(output)[:1200]
            st.text_area(
                f"Preview: {output.name}", value=preview, height=120, key=f"preview_{output.name}"
            )
        else:
            st.caption("Not generated yet.")


if __name__ == "__main__":
    main()

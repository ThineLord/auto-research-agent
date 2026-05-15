from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components
import yaml


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


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def tail_lines(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
        f"cd {CANONICAL_ROOT}\n"
        "source .venv/bin/activate\n"
        "streamlit run ui/app.py",
        language="bash",
    )


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def run_meta_path(proj_path: Path) -> Path:
    return proj_path / "ui_run_process.json"


def model_job_meta_path(proj_path: Path) -> Path:
    return proj_path / "ui_model_job_process.json"


def get_active_meta(meta_path: Path) -> Dict[str, Any]:
    meta = read_json(meta_path)
    pid = int(meta.get("pid", 0)) if meta else 0
    if pid and is_pid_running(pid):
        return meta
    if meta_path.exists():
        meta_path.unlink()
    return {}


def query_ollama_models() -> tuple[List[Dict[str, str]], Optional[str]]:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return [], "Ollama is not installed or not in PATH."
    except subprocess.SubprocessError as exc:
        return [], f"Failed to query Ollama: {exc}"

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or "Unknown error from ollama list."
        return [], f"Ollama is not available: {err}"

    models: List[Dict[str, str]] = []
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    for line in lines[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if not parts:
            continue
        name = parts[0] if len(parts) > 0 else ""
        model_id = parts[1] if len(parts) > 1 else ""
        size = parts[2] if len(parts) > 2 else ""
        modified = parts[3] if len(parts) > 3 else ""
        models.append(
            {
                "name": name,
                "id": model_id,
                "size": size,
                "modified": modified,
            }
        )
    return models, None


def load_default_model_name() -> str:
    if not CONFIG_PATH.exists():
        return "qwen3:8b"
    try:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return "qwen3:8b"
    model_cfg = config.get("model", {})
    if isinstance(model_cfg, dict):
        return str(model_cfg.get("name", "qwen3:8b"))
    if isinstance(model_cfg, str):
        return model_cfg
    return "qwen3:8b"


def save_default_model_name(model_name: str) -> Optional[str]:
    if not CONFIG_PATH.exists():
        return f"config file not found: {CONFIG_PATH}"
    try:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return f"failed to parse config.yaml: {exc}"
    model_cfg = config.get("model", {})
    if not isinstance(model_cfg, dict):
        model_cfg = {}
    model_cfg.setdefault("provider", "ollama")
    model_cfg["name"] = model_name
    model_cfg.setdefault("temperature", 0.3)
    model_cfg.setdefault("timeout_seconds", 300)
    config["model"] = model_cfg
    CONFIG_PATH.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return None


def start_background_process(
    *,
    command: List[str],
    cwd: Path,
    log_path: Path,
    meta_path: Path,
    kind: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        meta: Dict[str, Any] = {
            "pid": process.pid,
            "command": " ".join(command),
            "kind": kind,
            "started_at": datetime.now().isoformat(),
        }
        if extra:
            meta.update(extra)
        write_json(meta_path, meta)
        return process.pid
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to start {kind} process: {exc}")
        return None


def run_project_tests() -> Dict[str, Any]:
    started = time.monotonic()
    command = [
        sys.executable,
        "-m",
        "unittest",
        "tests.test_storage",
        "tests.test_round_loop",
        "-v",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part)
        return {
            "ok": False,
            "returncode": None,
            "elapsed": elapsed,
            "command": " ".join(command),
            "output": output or "Test run timed out after 120 seconds.",
        }

    elapsed = time.monotonic() - started
    output = "\n".join(part for part in [result.stdout, result.stderr] if part.strip())
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "elapsed": elapsed,
        "command": " ".join(command),
        "output": output.strip() or "(no test output)",
    }


def main() -> None:
    st.set_page_config(page_title="Auto Research Agent", layout="wide")
    st.title("Auto Research Agent")
    render_runtime_location_check()

    st.subheader("Quick Actions")
    quick_test_col, quick_status_col = st.columns([1, 3])
    with quick_test_col:
        if st.button("Run Tests", key="run_tests_quick"):
            st.session_state["test_result"] = run_project_tests()
    with quick_status_col:
        quick_test_result = st.session_state.get("test_result")
        if quick_test_result:
            if quick_test_result["ok"]:
                st.success(f"Tests passed in {quick_test_result['elapsed']:.2f}s")
            else:
                st.error(f"Tests failed in {quick_test_result['elapsed']:.2f}s")
        else:
            st.info("Click Run Tests to check the project without running Ollama.")

    projects = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()]) if PROJECTS_DIR.exists() else []
    default_index = projects.index("pama") if "pama" in projects else 0
    selected_project = st.selectbox("A. Project selector", projects, index=default_index if projects else None)
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
    run_meta = get_active_meta(run_meta_path(proj_path))
    model_job_meta = get_active_meta(model_job_meta_path(proj_path))

    col_input_left, col_input_right = st.columns(2)
    with col_input_left:
        task_text = st.text_area("B. Input editor - task.md", value=read_text(task_path), height=260)
    with col_input_right:
        memory_text = st.text_area("B. Input editor - memory.md", value=read_text(memory_path), height=260)
    if st.button("Save Input"):
        write_text(task_path, task_text)
        write_text(memory_path, memory_text)
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

    models, models_error = query_ollama_models()
    installed_model_names = [m["name"] for m in models]
    default_model = load_default_model_name()
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
            pid = start_background_process(
                command=[sys.executable, "-m", "src.main", "--diagnostic", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model},
            )
            if pid:
                st.success(f"Started diagnostic run with model `{model}` (PID {pid})")
    with c2:
        if st.button("Run Normal", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            pid = start_background_process(
                command=[sys.executable, "-m", "src.main", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model},
            )
            if pid:
                st.success(f"Started normal run with model `{model}` (PID {pid})")
    with c3:
        if st.button("Run Continuous", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            pid = start_background_process(
                command=[sys.executable, "-m", "src.main", "--continuous", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model},
            )
            if pid:
                st.success(f"Started continuous run with model `{model}` (PID {pid})")
    with c4:
        if st.button("Pause / Stop Safely", disabled=not run_active):
            write_text(stop_signal_path, "STOP_REQUESTED\n")
            st.warning(f"Stop signal created: `{stop_signal_path}`")
    with c5:
        if st.button("Resume", disabled=blocked or bool(models_error)):
            model = st.session_state.get("selected_model", default_model)
            pid = start_background_process(
                command=[sys.executable, "-m", "src.main", "--resume", "--model", model],
                cwd=ROOT,
                log_path=run_log_path,
                meta_path=run_meta_path(proj_path),
                kind="run",
                extra={"model": model},
            )
            if pid:
                st.success(f"Started resume run with model `{model}` (PID {pid})")
    with c6:
        if st.button("Run Tests", disabled=run_active, key="run_tests_top"):
            st.session_state["test_result"] = run_project_tests()

    st.subheader("Project Tests")
    st.caption("Run the local automated tests I added for storage helpers and the no-Ollama round loop.")
    test_col_left, test_col_right = st.columns([1, 3])
    with test_col_left:
        if st.button("Run Tests", disabled=run_active, key="run_tests_panel"):
            st.session_state["test_result"] = run_project_tests()
    with test_col_right:
        last_test = st.session_state.get("test_result")
        if last_test:
            if last_test["ok"]:
                st.success(
                    f"Tests passed in {last_test['elapsed']:.2f}s "
                    f"using `{last_test['command']}`"
                )
            else:
                returncode = last_test["returncode"]
                st.error(
                    f"Tests failed in {last_test['elapsed']:.2f}s "
                    f"(return code: {returncode})"
                )
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
        selected_model = st.text_input("Model selector (manual)", value=st.session_state["selected_model"])
        st.session_state["selected_model"] = selected_model.strip()

    if st.button("Save Selected Model as Default", disabled=bool(models_error)):
        model_to_save = st.session_state.get("selected_model", "").strip()
        if not model_to_save:
            st.error("Model name is empty.")
        else:
            err = save_default_model_name(model_to_save)
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
            pid = start_background_process(
                command=["ollama", "pull", pull_model_name],
                cwd=ROOT,
                log_path=model_job_log_path,
                meta_path=model_job_meta_path(proj_path),
                kind="model_pull",
                extra={"model": pull_model_name},
            )
            if pid:
                st.success(f"Started pulling model `{pull_model_name}` (PID {pid})")

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
            pid = start_background_process(
                command=["ollama", "rm", delete_target],
                cwd=ROOT,
                log_path=model_job_log_path,
                meta_path=model_job_meta_path(proj_path),
                kind="model_delete",
                extra={"model": delete_target},
            )
            if pid:
                st.success(f"Started deleting model `{delete_target}` (PID {pid})")

    st.subheader("D. Progress panel")
    checkpoint = {}
    if checkpoint_path.exists():
        checkpoint = read_json(checkpoint_path)
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
    st.code(tail_lines(run_log_path, max_lines=240) or "(no logs yet)", language="text")
    st.caption("Model operation logs")
    st.code(tail_lines(model_job_log_path, max_lines=120) or "(no model operation logs yet)", language="text")
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
            preview = read_text(output)[:1200]
            st.text_area(f"Preview: {output.name}", value=preview, height=120, key=f"preview_{output.name}")
        else:
            st.caption("Not generated yet.")


if __name__ == "__main__":
    main()

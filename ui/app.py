from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"


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


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def process_meta_path(proj_path: Path) -> Path:
    return proj_path / "ui_process.json"


def get_active_process_meta(proj_path: Path) -> Dict[str, Any]:
    meta_path = process_meta_path(proj_path)
    meta = read_json(meta_path)
    pid = int(meta.get("pid", 0)) if meta else 0
    if pid and is_pid_running(pid):
        return meta
    if meta_path.exists():
        meta_path.unlink()
    return {}


def mark_process_started(proj_path: Path, pid: int, command: str) -> None:
    write_json(
        process_meta_path(proj_path),
        {
            "pid": pid,
            "command": command,
            "started_at": datetime.now().isoformat(),
        },
    )


def clear_process_meta(proj_path: Path) -> None:
    meta_path = process_meta_path(proj_path)
    if meta_path.exists():
        meta_path.unlink()


def start_process(command: list[str], cwd: Path, log_path: Path, proj_path: Path) -> Optional[subprocess.Popen]:
    active_meta = get_active_process_meta(proj_path)
    if active_meta:
        st.warning(
            f"Another run is active (PID {active_meta.get('pid')}). "
            "Please stop it safely or wait for completion."
        )
        return None
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
        st.session_state["process"] = process
        st.session_state["process_log_file"] = log_file
        st.session_state["process_command"] = " ".join(command)
        mark_process_started(proj_path, process.pid, " ".join(command))
        return process
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to start process: {exc}")
        return None


def ensure_process_state(proj_path: Path) -> None:
    proc = st.session_state.get("process")
    if proc is None:
        get_active_process_meta(proj_path)
        return
    if proc.poll() is not None:
        log_file = st.session_state.get("process_log_file")
        if log_file:
            try:
                log_file.close()
            except Exception:
                pass
        st.session_state["process"] = None
        st.session_state["process_log_file"] = None
        clear_process_meta(proj_path)


def main() -> None:
    st.set_page_config(page_title="Auto Research Agent", layout="wide")
    st.title("Auto Research Agent")

    projects = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()]) if PROJECTS_DIR.exists() else []
    default_index = projects.index("pama") if "pama" in projects else 0
    selected_project = st.selectbox("A. Project selector", projects, index=default_index if projects else None)
    if not selected_project:
        st.warning("No project found under projects/.")
        return

    proj_path = project_path(selected_project)
    ensure_process_state(proj_path)
    st.write(f"Project path: `{proj_path}`")

    task_path = proj_path / "task.md"
    memory_path = proj_path / "memory.md"
    run_log_path = proj_path / "run.log"
    checkpoint_path = proj_path / "checkpoint.json"
    stop_signal_path = proj_path / "STOP_REQUESTED"
    active_meta = get_active_process_meta(proj_path)

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
    proc = st.session_state.get("process")
    session_running = proc is not None and proc.poll() is None
    meta_running = bool(active_meta)
    is_running = session_running or meta_running
    if is_running:
        command_display = (
            st.session_state.get("process_command", "")
            if session_running
            else str(active_meta.get("command", "unknown command"))
        )
        pid_display = proc.pid if session_running else active_meta.get("pid", "N/A")
        st.info(f"Running (PID {pid_display}): `{command_display}`")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("Run Diagnostic", disabled=is_running):
            start_process([sys.executable, "-m", "src.main", "--diagnostic"], ROOT, run_log_path, proj_path)
    with c2:
        if st.button("Run Normal", disabled=is_running):
            start_process([sys.executable, "-m", "src.main"], ROOT, run_log_path, proj_path)
    with c3:
        if st.button("Run Continuous", disabled=is_running):
            start_process([sys.executable, "-m", "src.main", "--continuous"], ROOT, run_log_path, proj_path)
    with c4:
        if st.button("Pause / Stop Safely"):
            write_text(stop_signal_path, "STOP_REQUESTED\n")
            st.warning(f"Stop signal created: `{stop_signal_path}`")
    with c5:
        if st.button("Resume", disabled=is_running):
            start_process([sys.executable, "-m", "src.main", "--resume"], ROOT, run_log_path, proj_path)

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

    st.subheader("E. Live logs panel")
    auto_refresh = st.checkbox("Auto refresh logs every 2 seconds", value=True)
    st.code(tail_lines(run_log_path, max_lines=240) or "(no logs yet)", language="text")
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

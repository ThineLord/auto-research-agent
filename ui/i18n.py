from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "en"
LANGUAGE_LABELS = {
    "en": "English",
    "zh": "中文",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "Auto Research Agent",
        "sidebar_interface": "Interface",
        "language_selector": "Language",
        "theme_selector": "Theme",
        "theme_day": "Day Mode",
        "theme_dark": "Dark Mode",
        "app_root_label": "App root",
        "advanced_paths": "Advanced paths",
        "current_root_path": "Current root",
        "canonical_root_path": "Canonical root",
        "canonical_root_success": "Running from the canonical project folder.",
        "canonical_root_error": (
            "This Streamlit app is not running from the canonical project folder. "
            "Stop this server and restart Streamlit from the path below."
        ),
        "using_example_config": (
            "config.yaml was not found. The UI is using config.example.yaml and the "
            "public-safe example project."
        ),
        "config_error": "Config error: {error}",
        "quick_actions": "Quick Actions",
        "run_tests": "Run Tests",
        "tests_passed_short": "Tests passed in {elapsed:.2f}s",
        "tests_failed_short": "Tests failed in {elapsed:.2f}s",
        "quick_tests_help": "Click Run Tests to check the project without running Ollama.",
        "project_selector": "A. Project selector",
        "no_project_found": "No project found under projects/.",
        "configured_project_missing": (
            "Configured project `{project}` was not found. Choose an existing project or create "
            "`projects/{project}/task.md`."
        ),
        "using_public_safe_project": (
            "Showing public-safe project `{selected}` by default. You can select another "
            "project manually."
        ),
        "project_path": "Project path (relative): `{path}`",
        "input_editor_task": "B. Input editor - task.md",
        "input_editor_memory": "B. Input editor - memory.md",
        "task_placeholder": (
            "# New Research Task\n\n"
            "Use this file to describe the question you want the agent to work on.\n\n"
            "## Goal\n\n"
            "Write a short research plan about a topic of your choice.\n\n"
            "## Background\n\n"
            "Add key context, assumptions, and constraints.\n\n"
            "## Requirements\n\n"
            "- Draft a clear problem statement.\n"
            "- Propose 2-3 possible approaches.\n"
            "- List evaluation criteria.\n"
            "- Identify risks or open questions.\n"
        ),
        "memory_placeholder": (
            "# Optional Project Memory\n\n"
            "Use this optional file for stable context that should be available in every run.\n\n"
            "Examples:\n"
            "- Domain constraints\n"
            "- Citation conventions\n"
            "- Preferred output structure\n"
            "- Known assumptions\n\n"
            "Leave this as a placeholder or replace it with your own notes before saving."
        ),
        "task_missing_help": "task.md does not exist yet. Saving will create it for this project.",
        "memory_optional_help": (
            "memory.md is optional and ignored by Git. Saving will create a local memory file."
        ),
        "save_input": "Save Input",
        "input_saved": "task.md and memory.md saved.",
        "run_controls": "C. Run controls",
        "run_active": "Run active (PID {pid}): `{command}`",
        "model_job_active": "Model job active (PID {pid}): `{command}`",
        "ollama_models_error_prefix": "Ollama model list error: {error}",
        "ollama_not_installed": "Ollama is not installed or not in PATH.",
        "ollama_query_failed": "Failed to query Ollama: {detail}",
        "ollama_unavailable": "Ollama is not available: {detail}",
        "selected_model": "Selected model: `{model}`",
        "run_diagnostic": "Run Diagnostic",
        "run_normal": "Run Normal",
        "run_continuous": "Run Continuous",
        "pause_stop_safely": "Pause / Stop Safely",
        "resume": "Resume",
        "started_diagnostic": "Started diagnostic run with model `{model}` (PID {pid})",
        "started_normal": "Started normal run with model `{model}` (PID {pid})",
        "started_continuous": "Started continuous run with model `{model}` (PID {pid})",
        "started_resume": "Started resume run with model `{model}` (PID {pid})",
        "stop_signal_created": "Stop signal created: `{path}`",
        "project_tests": "Project Tests",
        "project_tests_help": "Run the local automated tests without starting Ollama.",
        "tests_passed_detail": "Tests passed in {elapsed:.2f}s using `{command}`",
        "tests_failed_detail": "Tests failed in {elapsed:.2f}s (return code: {returncode})",
        "no_test_run": "No test run yet.",
        "test_output": "Test output",
        "model_management": "Model Management",
        "model_management_help": "Available to download: any valid Ollama model name.",
        "recommended_models": "Recommended models",
        "installed_models": "Installed models",
        "installed_tag": " (installed)",
        "model_default_balanced": "default balanced model",
        "model_stronger_slower": "stronger, slower",
        "model_reasoning_experiment": "reasoning-oriented experiment",
        "model_stable_fallback": "stable fallback",
        "no_installed_model": "No installed model found.",
        "models_table_name": "Name",
        "models_table_size": "Size",
        "models_table_modified": "Modified",
        "model_selector": "Model selector",
        "model_selector_manual": "Model selector (manual)",
        "check_model_health": "Check Model Health",
        "health_check_help": "Run a fast health check before starting long workflows.",
        "save_default_model": "Save Selected Model as Default",
        "model_name_empty": "Model name is empty.",
        "saved_default_model": "Saved `{model}` to config.yaml (model.name).",
        "pull_model_by_name": "Pull model by name",
        "pull_model": "Pull Model",
        "enter_model_name": "Please enter a model name.",
        "started_pull_model": "Started pulling model `{model}` (PID {pid})",
        "delete_model": "Delete model (installed)",
        "none_option": "(none)",
        "confirm_delete": "I understand deletion cannot be undone.",
        "delete_selected_model": "Delete Selected Model",
        "confirm_delete_first": "Please confirm deletion first.",
        "cannot_delete_running_model": "Cannot delete the model used by the currently running task.",
        "no_deletable_model": "No deletable model selected.",
        "started_delete_model": "Started deleting model `{model}` (PID {pid})",
        "progress_panel": "D. Progress panel",
        "auto_refresh_logs": "Auto refresh logs every 2 seconds",
        "metric_mode": "Mode",
        "metric_round": "Round",
        "metric_stage": "Stage",
        "metric_best_score": "Best score",
        "pid_line": "PID: `{pid}`",
        "model_line": "Model: `{model}`",
        "last_successful_agent": "Last successful agent: `{agent}`",
        "stop_reason": "Stop reason: `{reason}`",
        "stop_signal_present": "Stop signal present: `{present}`",
        "live_logs_panel": "E. Live logs panel",
        "no_logs_yet": "(no logs yet)",
        "model_operation_logs": "Model operation logs",
        "no_model_operation_logs": "(no model operation logs yet)",
        "output_browser": "F. Output browser",
        "output_file": "Output file",
        "not_generated_suffix": " (not generated)",
        "output_not_generated": "This output has not been generated yet.",
        "empty_markdown": "_Empty file._",
        "empty_text": "(empty file)",
        "output_best": "Best output",
        "output_final_report": "Final session report",
        "output_interrupted_report": "Interrupted report",
        "output_checkpoint": "Checkpoint",
        "output_score_history": "Score history",
        "output_run_log": "Run log",
        "output_model_ops_log": "Model operation log",
        "output_latest_draft": "Latest round draft",
        "output_latest_review": "Latest round review",
        "output_latest_revised": "Latest round revised",
        "output_latest_judge": "Latest round judge",
        "stage_idle": "Idle",
        "stage_starting": "starting",
        "stage_starting_round": "starting round",
        "stage_after_agent": "after {agent}",
        "resume_no_checkpoint": "No checkpoint exists yet. Run a workflow before resuming.",
        "resume_blocked_active": "A run is active. Resume is blocked until the current run exits.",
        "resume_model_note": (
            " Checkpoint model was `{checkpoint_model}`; selected model is `{selected_model}`."
        ),
        "resume_available": "Resume available from round {next_round}.{model_note}",
        "resume_unavailable": (
            "Resume is unavailable. Last stop reason: `{stop_reason}`.{model_note}"
        ),
        "health_no_model": "No model selected.",
        "health_timeout": "Ollama API timed out at {base_url}.",
        "health_api_unhealthy": "Ollama API is not healthy at {base_url}: {error}",
        "health_model_missing": "Ollama is reachable, but `{model}` is not installed.",
        "health_model_ok": "Ollama is reachable and `{model}` is installed.",
        "process_error_prefix": "Process failed to start: {error}",
    },
    "zh": {
        "app_title": "Auto Research Agent",
        "sidebar_interface": "界面设置",
        "language_selector": "语言",
        "theme_selector": "主题",
        "theme_day": "Day Mode（日间模式）",
        "theme_dark": "Dark Mode（深色模式）",
        "app_root_label": "应用根目录",
        "advanced_paths": "高级路径",
        "current_root_path": "当前根目录",
        "canonical_root_path": "标准根目录",
        "canonical_root_success": "当前正在从标准项目目录运行。",
        "canonical_root_error": (
            "这个 Streamlit 应用没有从标准项目目录启动。请停止当前服务，再从下面的路径重新启动。"
        ),
        "using_example_config": (
            "没有找到 config.yaml。UI 正在使用 config.example.yaml，并默认打开安全示例项目。"
        ),
        "config_error": "配置错误：{error}",
        "quick_actions": "快捷操作",
        "run_tests": "运行测试",
        "tests_passed_short": "测试通过，用时 {elapsed:.2f} 秒",
        "tests_failed_short": "测试失败，用时 {elapsed:.2f} 秒",
        "quick_tests_help": "点击“运行测试”，可在不启动 Ollama 的情况下检查项目。",
        "project_selector": "A. 选择项目",
        "no_project_found": "projects/ 目录下没有找到项目。",
        "configured_project_missing": (
            "配置中的项目 `{project}` 不存在。请选择已有项目，或创建 `projects/{project}/task.md`。"
        ),
        "using_public_safe_project": (
            "默认显示安全示例项目 `{selected}`。你仍然可以手动选择其他项目。"
        ),
        "project_path": "项目路径（相对路径）：`{path}`",
        "input_editor_task": "B. 输入编辑器 - task.md",
        "input_editor_memory": "B. 输入编辑器 - memory.md",
        "task_placeholder": (
            "# 新研究任务\n\n"
            "在这里描述你希望 agent 研究或规划的问题。\n\n"
            "## 目标\n\n"
            "围绕你选择的主题，写一个简短研究计划。\n\n"
            "## 背景\n\n"
            "补充关键上下文、假设和限制。\n\n"
            "## 要求\n\n"
            "- 写出清晰的问题陈述。\n"
            "- 提出 2-3 个可能方案。\n"
            "- 列出评估标准。\n"
            "- 识别风险或未解决问题。\n"
        ),
        "memory_placeholder": (
            "# 可选项目记忆\n\n"
            "这里可以写每次运行都应该知道的稳定上下文。\n\n"
            "示例：\n"
            "- 领域限制\n"
            "- 引用格式\n"
            "- 偏好的输出结构\n"
            "- 已知假设\n\n"
            "如果暂时不需要，可以保留占位内容；点击保存后才会创建本地 memory.md。"
        ),
        "task_missing_help": "task.md 还不存在。点击保存后会为当前项目创建它。",
        "memory_optional_help": "memory.md 是可选文件，并且会被 Git 忽略。点击保存后才会创建本地记忆文件。",
        "save_input": "保存输入",
        "input_saved": "task.md 和 memory.md 已保存。",
        "run_controls": "C. 运行控制",
        "run_active": "任务正在运行（PID {pid}）：`{command}`",
        "model_job_active": "模型任务正在运行（PID {pid}）：`{command}`",
        "ollama_models_error_prefix": "Ollama 模型列表读取失败：{error}",
        "ollama_not_installed": "Ollama 未安装，或不在 PATH 中。",
        "ollama_query_failed": "查询 Ollama 失败：{detail}",
        "ollama_unavailable": "Ollama 当前不可用：{detail}",
        "selected_model": "当前模型：`{model}`",
        "run_diagnostic": "运行诊断 / Run Diagnostic",
        "run_normal": "正常运行 / Run Normal",
        "run_continuous": "连续运行 / Run Continuous",
        "pause_stop_safely": "安全暂停 / Pause",
        "resume": "恢复 / Resume",
        "started_diagnostic": "已使用模型 `{model}` 启动诊断运行（PID {pid}）",
        "started_normal": "已使用模型 `{model}` 启动正常运行（PID {pid}）",
        "started_continuous": "已使用模型 `{model}` 启动连续运行（PID {pid}）",
        "started_resume": "已使用模型 `{model}` 启动恢复运行（PID {pid}）",
        "stop_signal_created": "已创建安全停止信号：`{path}`",
        "project_tests": "项目测试",
        "project_tests_help": "运行本地自动化测试，不会启动 Ollama。",
        "tests_passed_detail": "测试通过，用时 {elapsed:.2f} 秒，命令：`{command}`",
        "tests_failed_detail": "测试失败，用时 {elapsed:.2f} 秒（返回码：{returncode}）",
        "no_test_run": "还没有运行测试。",
        "test_output": "测试输出",
        "model_management": "模型管理",
        "model_management_help": "可以下载任何有效的 Ollama 模型名。",
        "recommended_models": "推荐模型",
        "installed_models": "已安装模型",
        "installed_tag": "（已安装）",
        "model_default_balanced": "默认均衡模型",
        "model_stronger_slower": "能力更强，速度更慢",
        "model_reasoning_experiment": "偏推理实验",
        "model_stable_fallback": "稳定备用模型",
        "no_installed_model": "没有发现已安装模型。",
        "models_table_name": "模型名",
        "models_table_size": "大小",
        "models_table_modified": "更新时间",
        "model_selector": "模型选择",
        "model_selector_manual": "模型选择（手动输入）",
        "check_model_health": "检查模型状态",
        "health_check_help": "开始长任务前，建议先做一次快速健康检查。",
        "save_default_model": "保存为默认模型",
        "model_name_empty": "模型名为空。",
        "saved_default_model": "已将 `{model}` 保存到 config.yaml（model.name）。",
        "pull_model_by_name": "按名称拉取模型",
        "pull_model": "拉取模型",
        "enter_model_name": "请输入模型名。",
        "started_pull_model": "已开始拉取模型 `{model}`（PID {pid}）",
        "delete_model": "删除模型（已安装）",
        "none_option": "（无）",
        "confirm_delete": "我确认删除后无法撤销。",
        "delete_selected_model": "删除选中模型",
        "confirm_delete_first": "请先勾选确认删除。",
        "cannot_delete_running_model": "不能删除当前运行任务正在使用的模型。",
        "no_deletable_model": "没有可删除的模型。",
        "started_delete_model": "已开始删除模型 `{model}`（PID {pid}）",
        "progress_panel": "D. 进度面板",
        "auto_refresh_logs": "每 2 秒自动刷新日志",
        "metric_mode": "模式",
        "metric_round": "轮次",
        "metric_stage": "阶段",
        "metric_best_score": "最佳分数",
        "pid_line": "PID：`{pid}`",
        "model_line": "模型：`{model}`",
        "last_successful_agent": "上一个成功 Agent：`{agent}`",
        "stop_reason": "停止原因：`{reason}`",
        "stop_signal_present": "停止信号存在：`{present}`",
        "live_logs_panel": "E. 实时日志",
        "no_logs_yet": "（暂无日志）",
        "model_operation_logs": "模型操作日志",
        "no_model_operation_logs": "（暂无模型操作日志）",
        "output_browser": "F. 输出浏览器",
        "output_file": "输出文件",
        "not_generated_suffix": "（尚未生成）",
        "output_not_generated": "这个输出还没有生成。",
        "empty_markdown": "_空文件。_",
        "empty_text": "（空文件）",
        "output_best": "最佳输出",
        "output_final_report": "最终会话报告",
        "output_interrupted_report": "中断报告",
        "output_checkpoint": "检查点",
        "output_score_history": "评分历史",
        "output_run_log": "运行日志",
        "output_model_ops_log": "模型操作日志",
        "output_latest_draft": "最新轮草稿",
        "output_latest_review": "最新轮审查",
        "output_latest_revised": "最新轮修订稿",
        "output_latest_judge": "最新轮评分",
        "stage_idle": "空闲",
        "stage_starting": "正在启动",
        "stage_starting_round": "正在开始新一轮",
        "stage_after_agent": "{agent} 之后",
        "resume_no_checkpoint": "还没有检查点。请先运行一次工作流，再尝试恢复。",
        "resume_blocked_active": "当前有任务正在运行。请等它退出后再恢复。",
        "resume_model_note": "检查点模型是 `{checkpoint_model}`；当前选择的是 `{selected_model}`。",
        "resume_available": "可以从第 {next_round} 轮恢复。{model_note}",
        "resume_unavailable": "当前不能恢复。上次停止原因：`{stop_reason}`。{model_note}",
        "health_no_model": "还没有选择模型。",
        "health_timeout": "Ollama API 在 {base_url} 超时。",
        "health_api_unhealthy": "Ollama API 在 {base_url} 不健康：{error}",
        "health_model_missing": "Ollama 可以连接，但 `{model}` 尚未安装。",
        "health_model_ok": "Ollama 可以连接，且 `{model}` 已安装。",
        "process_error_prefix": "进程启动失败：{error}",
    },
}


def normalize_language(language: str | None) -> str:
    if language in LANGUAGE_LABELS:
        return str(language)
    return DEFAULT_LANGUAGE


def translate(language: str | None, key: str, **kwargs: Any) -> str:
    language = normalize_language(language)
    template = TRANSLATIONS[language].get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))
    return template.format(**kwargs)

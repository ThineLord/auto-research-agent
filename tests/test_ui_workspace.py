"""UI regression checks with isolated artifacts and no model calls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import ui.app as app
from ui.i18n import TRANSLATIONS
from ui.theme import THEME_VALUES


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    projects = tmp_path / "projects"
    project = projects / "example"
    project.mkdir(parents=True)
    (project / "task.md").write_text("A saved brief", encoding="utf-8")
    (project / "memory.md").write_text("Saved context", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(app.CONFIG_EXAMPLE_PATH.read_text(), encoding="utf-8")
    monkeypatch.setattr(app, "PROJECTS_DIR", projects)
    monkeypatch.setattr(app, "CONFIG_PATH", config)
    monkeypatch.setattr(
        app,
        "query_ollama_models",
        lambda **_: ([{"name": "qwen3:8b", "size": "5 GB", "modified": "today"}], ""),
    )
    launch = Mock(return_value=SimpleNamespace(error=None, pid=1234))
    monkeypatch.setattr(app, "start_background_process", launch)
    at = AppTest.from_string("from ui.app import main\nmain()", default_timeout=15).run()
    assert not at.exception
    return at, project, launch


def test_preferences_preserve_unsaved_inputs_and_selected_mode(workspace):
    at, project, launch = workspace
    at.text_area(key="task_editor_example").set_value("Unsaved idea / 未保存的想法").run()
    at.text_area(key="memory_editor_example").set_value("Unsaved context / 背景").run()
    at.selectbox(key="_choice_run_mode_en").select("continuous").run()
    for language, theme in [("zh", "dark"), ("en", "day"), ("zh", "day"), ("en", "dark")]:
        at.selectbox(key="ui_language").select(language).run()
        at.radio(key=f"_choice_ui_theme_{language}").set_value(theme).run()
        assert not at.exception
        assert at.text_area(key="task_editor_example").value == "Unsaved idea / 未保存的想法"
        assert at.text_area(key="memory_editor_example").value == "Unsaved context / 背景"
        assert at.selectbox(key=f"_choice_run_mode_{language}").value == "continuous"
        assert at.radio(key=f"_choice_ui_theme_{language}").value == theme
        assert at.tabs[0].label == TRANSLATIONS[language]["nav_workspace"]
        assert any(THEME_VALUES[theme]["app_bg"] in element.value for element in at.markdown)
    assert (project / "task.md").read_text() == "A saved brief"
    launch.assert_not_called()


@pytest.mark.parametrize(
    "mode,flag", [("normal", None), ("continuous", "--continuous"), ("diagnostic", "--diagnostic")]
)
def test_consolidated_start_dispatches_original_modes(workspace, mode, flag):
    at, _, launch = workspace
    at.selectbox(key="_choice_run_mode_en").select(mode).run()
    at.button(key="start_run").click().run()
    assert not at.exception
    launch.assert_called_once()
    command = launch.call_args.kwargs["command"]
    assert launch.call_args.kwargs["extra"]["mode"] == mode
    if flag:
        assert flag in command
    else:
        assert "--continuous" not in command and "--diagnostic" not in command


def test_navigation_and_single_test_entry_preserve_existing_tools(workspace):
    at, _, launch = workspace
    assert [tab.label for tab in at.tabs] == ["Workspace", "Outputs", "Insights", "Settings"]
    assert len([button for button in at.button if button.label == "Run Tests"]) == 1
    assert not any(button.label == "Run Tests" for button in at.tabs[0].button)
    assert at.button(key="resume_run").disabled
    assert at.button(key="stop_run").disabled
    assert {"Pull Model", "Delete Selected Model", "Check Model Health"} <= {
        b.label for b in at.tabs[3].button
    }
    at.selectbox(key="_choice_selected_provider_en").select("gemini").run()
    assert not at.exception
    assert {"Discover free cloud models", "Profile safe free models", "Check Gemini Health"} <= {
        b.label for b in at.tabs[3].button
    }
    launch.assert_not_called()


def test_translations_have_matching_keys_and_placeholders():
    from string import Formatter

    assert TRANSLATIONS["en"].keys() == TRANSLATIONS["zh"].keys()

    def fields(value):
        return {field for _, field, _, _ in Formatter().parse(value) if field}

    for key in TRANSLATIONS["en"]:
        assert fields(TRANSLATIONS["en"][key]) == fields(TRANSLATIONS["zh"][key]), key

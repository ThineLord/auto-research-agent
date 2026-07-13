from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import InvalidURL
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

import src.config as config_module
import src.runtime as runtime_module
from src.config import (
    list_installed_ollama_models,
    load_default_model_name,
    parse_ollama_list_output,
    parse_ollama_tags_payload,
    query_ollama_models,
    save_default_model_name,
)
from src.runtime import (
    acquire_run_lock,
    get_active_process_meta,
    release_run_lock,
    run_project_tests,
    start_background_process,
    stop_requested,
)
from src.storage import (
    ensure_project_runtime_paths_safe,
    read_file_text,
    read_json_file,
    tail_file_lines,
    write_file_text,
    write_json_file,
)


class SharedUiBackendHelperTests(unittest.TestCase):
    def test_text_json_and_tail_helpers_handle_missing_and_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = root / "nested" / "note.txt"
            json_path = root / "state.json"
            invalid_json_path = root / "invalid.json"
            log_path = root / "run.log"
            stale_text_path = root / "stale.txt"

            self.assertEqual(read_file_text(text_path), "")
            write_file_text(text_path, "hello\n")
            self.assertEqual(read_file_text(text_path), "hello\n")
            stale_text_path.mkdir()
            self.assertEqual(read_file_text(stale_text_path), "")

            self.assertEqual(read_json_file(json_path), {})
            write_json_file(json_path, {"round": 3})
            self.assertEqual(read_json_file(json_path), {"round": 3})

            invalid_json_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(read_json_file(invalid_json_path), {})

            log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            self.assertEqual(tail_file_lines(log_path, max_lines=2), "two\nthree")
            self.assertEqual(tail_file_lines(root / "missing.log"), "")
            stale_log_path = root / "stale.log"
            stale_log_path.mkdir()
            self.assertEqual(tail_file_lines(stale_log_path), "")

    def test_score_history_loader_tolerates_stale_directory_path(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            score_history_path = Path(tmp) / "score_history.json"
            score_history_path.mkdir()

            self.assertEqual(ui_app.load_score_history_rows(score_history_path), [])

    def test_cloud_free_session_cache_reloads_when_selected_project_changes(self) -> None:
        import ui.app as ui_app
        from src.cloud_free import (
            CloudModelProfile,
            classify_model,
            save_discovery_artifact,
            save_profile_artifact,
        )

        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project_a = projects / "project-a"
            project_b = projects / "project-b"
            project_a.mkdir(parents=True)
            project_b.mkdir()
            for project, label, latency in (
                (project_a, "Project A metadata", 1.0),
                (project_b, "Project B metadata", 2.0),
            ):
                save_discovery_artifact(
                    project,
                    [classify_model(model_id="gemini-3.5-flash", display_name=label)],
                )
                save_profile_artifact(
                    project,
                    [
                        CloudModelProfile(
                            model_id="gemini-3.5-flash",
                            reachable=True,
                            latency_seconds=latency,
                        )
                    ],
                )

            session_state: dict[str, object] = {
                "cloud_free_discovered_models": [
                    classify_model(
                        model_id="gemini-3.5-flash",
                        display_name="legacy global cache",
                    )
                ],
                "cloud_free_profile_results": [
                    CloudModelProfile(model_id="gemini-3.5-flash", latency_seconds=99.0)
                ],
            }
            models_a, profiles_a = ui_app.load_scoped_cloud_free_cache(
                project_a,
                session_state,
            )
            identity_a = session_state["cloud_free_cache_identity"]
            models_b, profiles_b = ui_app.load_scoped_cloud_free_cache(
                project_b,
                session_state,
            )
            identity_b = session_state["cloud_free_cache_identity"]
            models_a_again, profiles_a_again = ui_app.load_scoped_cloud_free_cache(
                project_a,
                session_state,
            )

        self.assertEqual(models_a[0].display_name, "Project A metadata")
        self.assertEqual(profiles_a[0].latency_seconds, 1.0)
        self.assertEqual(models_b[0].display_name, "Project B metadata")
        self.assertEqual(profiles_b[0].latency_seconds, 2.0)
        self.assertNotEqual(identity_a, identity_b)
        self.assertEqual(models_a_again[0].display_name, "Project A metadata")
        self.assertEqual(profiles_a_again[0].latency_seconds, 1.0)

    def test_cloud_free_session_cache_reloads_external_same_id_metadata_updates(self) -> None:
        import ui.app as ui_app
        from src.cloud_free import (
            CloudModelProfile,
            classify_model,
            recommend_free_cloud_model,
            save_discovery_artifact,
            save_profile_artifact,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "selected"
            project.mkdir(parents=True)
            save_discovery_artifact(
                project,
                [
                    classify_model(
                        model_id="gemini-3.5-flash",
                        display_name="old metadata",
                    )
                ],
            )
            save_profile_artifact(
                project,
                [
                    CloudModelProfile(
                        model_id="gemini-3.5-flash",
                        daily_quota_exhausted=True,
                        latency_seconds=1.0,
                    )
                ],
            )
            session_state: dict[str, object] = {}
            old_models, old_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                session_state,
            )

            with (
                patch.object(ui_app, "load_discovery_artifact") as load_discovery,
                patch.object(ui_app, "load_profile_artifact") as load_profile,
            ):
                cached_models, cached_profiles = ui_app.load_scoped_cloud_free_cache(
                    project,
                    session_state,
                )
            load_discovery.assert_not_called()
            load_profile.assert_not_called()

            self.assertIsNone(
                recommend_free_cloud_model(
                    candidates=old_models,
                    profiles=old_profiles,
                )
            )
            discovery_path = project / "artifacts" / "cloud_free_models.json"
            original_discovery = discovery_path.read_text(encoding="utf-8")
            updated_discovery = original_discovery.replace("old metadata", "new metadata")
            self.assertEqual(len(updated_discovery), len(original_discovery))
            discovery_before = discovery_path.stat()
            discovery_path.write_text(updated_discovery, encoding="utf-8")
            os.utime(
                discovery_path,
                ns=(discovery_before.st_atime_ns, discovery_before.st_mtime_ns),
            )
            discovery_after = discovery_path.stat()
            self.assertEqual(
                (
                    discovery_after.st_ino,
                    discovery_after.st_size,
                    discovery_after.st_mtime_ns,
                ),
                (
                    discovery_before.st_ino,
                    discovery_before.st_size,
                    discovery_before.st_mtime_ns,
                ),
            )
            refreshed_models, unchanged_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                session_state,
            )
            save_profile_artifact(
                project,
                [
                    CloudModelProfile(
                        model_id="gemini-3.5-flash",
                        reachable=True,
                        latency_seconds=9.0,
                    )
                ],
            )
            unchanged_models, refreshed_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                session_state,
            )

        self.assertIs(cached_models, old_models)
        self.assertIs(cached_profiles, old_profiles)
        self.assertEqual(refreshed_models[0].model_id, old_models[0].model_id)
        self.assertEqual(refreshed_models[0].display_name, "new metadata")
        self.assertEqual(unchanged_profiles[0].latency_seconds, 1.0)
        self.assertEqual(unchanged_models[0].display_name, "new metadata")
        self.assertEqual(refreshed_profiles[0].model_id, old_profiles[0].model_id)
        self.assertEqual(refreshed_profiles[0].latency_seconds, 9.0)
        self.assertIsNotNone(
            recommend_free_cloud_model(
                candidates=unchanged_models,
                profiles=refreshed_profiles,
            )
        )

    def test_cloud_free_session_cache_retries_unstable_snapshots_then_fails_empty(self) -> None:
        import ui.app as ui_app

        project = Path("unused-project")
        stable_session: dict[str, object] = {
            "cloud_free_cache_identity": ("old",),
            "cloud_free_discovered_models": ["old-model"],
            "cloud_free_profile_results": ["old-profile"],
        }
        with (
            patch.object(
                ui_app,
                "cloud_free_cache_identity",
                side_effect=[("generation-a",), ("generation-b",), ("generation-b",)],
            ),
            patch.object(
                ui_app,
                "load_discovery_artifact",
                side_effect=[["first-model"], ["stable-model"]],
            ) as load_discovery,
            patch.object(
                ui_app,
                "load_profile_artifact",
                side_effect=[["first-profile"], ["stable-profile"]],
            ) as load_profile,
        ):
            stable_models, stable_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                stable_session,
            )

        self.assertEqual(stable_models, ["stable-model"])
        self.assertEqual(stable_profiles, ["stable-profile"])
        self.assertEqual(stable_session["cloud_free_cache_identity"], ("generation-b",))
        self.assertEqual(load_discovery.call_count, 2)
        self.assertEqual(load_profile.call_count, 2)

        unstable_session: dict[str, object] = {
            "cloud_free_cache_identity": ("old",),
            "cloud_free_discovered_models": ["old-model"],
            "cloud_free_profile_results": ["old-profile"],
        }
        with (
            patch.object(
                ui_app,
                "cloud_free_cache_identity",
                side_effect=[("generation-a",), ("generation-b",), ("generation-c",)],
            ),
            patch.object(
                ui_app,
                "load_discovery_artifact",
                side_effect=[["first-model"], ["second-model"]],
            ),
            patch.object(
                ui_app,
                "load_profile_artifact",
                side_effect=[["first-profile"], ["second-profile"]],
            ),
        ):
            unstable_models, unstable_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                unstable_session,
            )

        self.assertEqual(unstable_models, [])
        self.assertEqual(unstable_profiles, [])
        self.assertNotIn("cloud_free_cache_identity", unstable_session)
        self.assertNotIn("cloud_free_discovered_models", unstable_session)
        self.assertNotIn("cloud_free_profile_results", unstable_session)

    def test_cloud_free_session_cache_recovers_from_unreadable_artifacts(self) -> None:
        import ui.app as ui_app
        from src.cloud_free import (
            CloudModelProfile,
            classify_model,
            save_discovery_artifact,
            save_profile_artifact,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "selected"
            artifacts = project / "artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / "cloud_free_models.json").write_bytes(b"\xff\xfe")
            (artifacts / "cloud_free_profile.json").write_text("{invalid", encoding="utf-8")
            session_state: dict[str, object] = {
                "cloud_free_discovered_models": ["stale-model"],
                "cloud_free_profile_results": ["stale-profile"],
            }

            invalid_models, invalid_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                session_state,
            )
            save_discovery_artifact(
                project,
                [classify_model(model_id="gemini-3.5-flash")],
            )
            save_profile_artifact(
                project,
                [CloudModelProfile(model_id="gemini-3.5-flash", reachable=True)],
            )
            valid_models, valid_profiles = ui_app.load_scoped_cloud_free_cache(
                project,
                session_state,
            )

        self.assertEqual(invalid_models, [])
        self.assertEqual(invalid_profiles, [])
        self.assertEqual(valid_models[0].model_id, "gemini-3.5-flash")
        self.assertEqual(valid_profiles[0].model_id, "gemini-3.5-flash")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_cloud_free_session_cache_clears_stale_values_for_unsafe_artifact(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "selected"
            artifacts = project / "artifacts"
            artifacts.mkdir(parents=True)
            external = root / "external-models.json"
            external.write_text('{"models": [{"private": true}]}\n', encoding="utf-8")
            (artifacts / "cloud_free_models.json").symlink_to(external)
            session_state: dict[str, object] = {
                "cloud_free_cache_identity": ("safe-old-project",),
                "cloud_free_discovered_models": ["stale-model"],
                "cloud_free_profile_results": ["stale-profile"],
            }

            models, profiles = ui_app.load_scoped_cloud_free_cache(project, session_state)

            self.assertEqual(
                external.read_text(encoding="utf-8"), '{"models": [{"private": true}]}\n'
            )

        self.assertEqual(models, [])
        self.assertEqual(profiles, [])
        self.assertNotIn("cloud_free_cache_identity", session_state)
        self.assertNotIn("cloud_free_discovered_models", session_state)
        self.assertNotIn("cloud_free_profile_results", session_state)

    def test_get_active_process_meta_returns_live_process_and_removes_stale_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "ui_run_process.json"
            write_json_file(meta_path, {"pid": 123, "command": "run"})

            with patch.object(runtime_module, "is_pid_running", return_value=True):
                self.assertEqual(get_active_process_meta(meta_path)["pid"], 123)

            write_json_file(meta_path, {"pid": 123, "command": "run"})
            with patch.object(runtime_module, "is_pid_running", return_value=False):
                self.assertEqual(get_active_process_meta(meta_path), {})

            self.assertFalse(meta_path.exists())

    def test_get_active_process_meta_tolerates_stale_directory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "ui_run_process.json"
            meta_path.mkdir()

            self.assertEqual(get_active_process_meta(meta_path), {})
            self.assertTrue(meta_path.exists())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_get_active_process_meta_rejects_linked_project_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            external_meta = outside_project / "ui_run_process.json"
            external_meta.write_text('{"pid": 0, "private": true}\n', encoding="utf-8")
            (root / "projects").symlink_to(
                root / "outside-projects",
                target_is_directory=True,
            )
            meta_path = root / "projects" / "selected" / "ui_run_process.json"

            with patch.object(
                runtime_module,
                "read_json_file",
                side_effect=AssertionError("external metadata must not be read"),
            ) as read_meta:
                self.assertEqual(get_active_process_meta(meta_path), {})

            read_meta.assert_not_called()
            self.assertEqual(
                external_meta.read_text(encoding="utf-8"),
                '{"pid": 0, "private": true}\n',
            )

    def test_is_pid_running_treats_zombie_process_as_stale(self) -> None:
        with (
            patch.object(runtime_module.os, "kill"),
            patch.object(
                runtime_module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="Z+\n"),
            ),
        ):
            self.assertFalse(runtime_module.is_pid_running(123))

        with (
            patch.object(runtime_module.os, "kill"),
            patch.object(
                runtime_module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="S+\n"),
            ),
        ):
            self.assertTrue(runtime_module.is_pid_running(123))

        with patch.object(runtime_module.os, "kill", side_effect=PermissionError):
            self.assertTrue(runtime_module.is_pid_running(123))

        with patch.object(runtime_module.os, "kill") as kill:
            self.assertFalse(runtime_module.is_pid_running(2**63))
        kill.assert_not_called()

        with (
            patch.object(runtime_module.os, "name", "nt"),
            patch.object(
                runtime_module,
                "_is_windows_pid_running",
                return_value=True,
            ) as windows_probe,
            patch.object(runtime_module.os, "kill") as kill,
        ):
            self.assertTrue(runtime_module.is_pid_running(456))
        windows_probe.assert_called_once_with(456)
        kill.assert_not_called()

    def test_start_background_process_writes_meta_and_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "run.log"
            meta_path = root / "ui_run_process.json"

            with patch.object(
                runtime_module.subprocess,
                "Popen",
                return_value=SimpleNamespace(pid=456),
            ) as popen:
                result = start_background_process(
                    command=["python", "-m", "src.main"],
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                    extra={"model": "qwen3:8b"},
                    env_overrides={"GEMINI_API_KEY": "secret-key"},
                )

            self.assertEqual(result.pid, 456)
            self.assertIsNone(result.error)
            self.assertEqual(popen.call_args.kwargs["env"]["GEMINI_API_KEY"], "secret-key")
            self.assertEqual(read_json_file(meta_path)["pid"], 456)
            self.assertEqual(read_json_file(meta_path)["model"], "qwen3:8b")
            meta_text = meta_path.read_text(encoding="utf-8")
            self.assertNotIn("secret-key", meta_text)
            self.assertNotIn("env_overrides", meta_text)

            with patch.object(
                runtime_module.subprocess,
                "Popen",
                side_effect=OSError("boom"),
            ):
                result = start_background_process(
                    command=["bad"],
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                )

            self.assertIsNone(result.pid)
            self.assertIn("Failed to start run process", result.error or "")

    def test_ui_session_credential_stays_in_child_environment_only(self) -> None:
        import ui.app as ui_app

        transport_env = "AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY"
        session_secret = "synthetic-ui-session-credential"
        inherited_secret = "synthetic-inherited-google-credential"
        stale_transport_secret = "synthetic-stale-ui-credential"
        command = ui_app.build_run_command(
            provider="gemini",
            mode="diagnostic",
            model="gemini-test",
            gemini_api_key_env="TEAM_GEMINI_KEY",
            project="selected",
            gemini_api_key_override_env=transport_env,
        )
        env_overrides = ui_app.build_provider_env_overrides(
            provider="gemini",
            api_key_env="TEAM_GEMINI_KEY",
            api_key_value=session_secret,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "run.log"
            meta_path = root / "ui_run_process.json"
            with (
                patch.dict(
                    runtime_module.os.environ,
                    {
                        "GOOGLE_API_KEY": inherited_secret,
                        transport_env: stale_transport_secret,
                    },
                    clear=True,
                ),
                patch.object(
                    runtime_module.subprocess,
                    "Popen",
                    return_value=SimpleNamespace(pid=456),
                ) as popen,
            ):
                result = start_background_process(
                    command=command,
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                    env_overrides=env_overrides,
                )

            child_command = popen.call_args.args[0]
            child_env = popen.call_args.kwargs["env"]
            meta_text = meta_path.read_text(encoding="utf-8")
            self.assertEqual(result.pid, 456)
            self.assertEqual(child_env[transport_env], session_secret)
            self.assertEqual(child_env["GOOGLE_API_KEY"], inherited_secret)
            self.assertIn("--gemini-api-key-override-env", child_command)
            self.assertIn(transport_env, child_command)
            for secret in (session_secret, inherited_secret, stale_transport_secret):
                with self.subTest(secret_kind=secret.split("-")[1]):
                    self.assertFalse(
                        any(secret in str(argument) for argument in child_command),
                        "credential retained in child argv",
                    )
                    self.assertNotIn(secret, meta_text)

            empty_overrides = ui_app.build_provider_env_overrides(
                provider="gemini",
                api_key_env="TEAM_GEMINI_KEY",
                api_key_value="   ",
            )
            with (
                patch.dict(
                    runtime_module.os.environ,
                    {transport_env: stale_transport_secret},
                    clear=True,
                ),
                patch.object(
                    runtime_module.subprocess,
                    "Popen",
                    return_value=SimpleNamespace(pid=789),
                ) as empty_popen,
            ):
                empty_result = start_background_process(
                    command=ui_app.build_run_command(
                        provider="gemini",
                        mode="diagnostic",
                        model="gemini-test",
                        gemini_api_key_env="TEAM_GEMINI_KEY",
                        project="selected",
                    ),
                    cwd=root,
                    log_path=root / "empty.log",
                    meta_path=root / "empty-process.json",
                    kind="run",
                    env_overrides=empty_overrides,
                )

            self.assertEqual(empty_result.pid, 789)
            self.assertEqual(empty_popen.call_args.kwargs["env"][transport_env], "")
            self.assertNotIn(
                "--gemini-api-key-override-env",
                empty_popen.call_args.args[0],
            )

    def test_start_background_process_masks_stale_log_path_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "run.log"
            log_path.mkdir()

            result = start_background_process(
                command=["python", "-c", "print(1)"],
                cwd=root,
                log_path=log_path,
                meta_path=root / "ui_run_process.json",
                kind="run",
            )

            self.assertIsNone(result.pid)
            self.assertIn("Failed to start run process", result.error or "")
            self.assertIn("IsADirectoryError", result.error or "")
            self.assertNotIn(str(root), result.error or "")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_start_background_process_rejects_unsafe_meta_before_popen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external_meta = root / "external-meta.json"
            external_meta.write_text('{"private": true}\n', encoding="utf-8")
            meta_path = root / "ui_run_process.json"
            meta_path.symlink_to(external_meta)

            with patch.object(runtime_module.subprocess, "Popen") as popen:
                result = start_background_process(
                    command=["python", "-c", "print(1)"],
                    cwd=root,
                    log_path=root / "run.log",
                    meta_path=meta_path,
                    kind="run",
                )

            popen.assert_not_called()
            self.assertIsNone(result.pid)
            self.assertEqual(external_meta.read_text(encoding="utf-8"), '{"private": true}\n')

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_start_background_process_rejects_linked_project_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            (root / "projects").symlink_to(
                root / "outside-projects",
                target_is_directory=True,
            )
            project_dir = root / "projects" / "selected"

            with patch.object(runtime_module.subprocess, "Popen") as popen:
                result = start_background_process(
                    command=["python", "-c", "print(1)"],
                    cwd=root,
                    log_path=project_dir / "run.log",
                    meta_path=project_dir / "ui_run_process.json",
                    kind="run",
                )

            popen.assert_not_called()
            self.assertIsNone(result.pid)
            self.assertFalse((outside_project / "run.log").exists())
            self.assertFalse((outside_project / "ui_run_process.json").exists())

    def test_start_background_process_cleans_up_if_meta_persistence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process = MagicMock(pid=456)

            with (
                patch.object(runtime_module.subprocess, "Popen", return_value=process),
                patch.object(
                    runtime_module,
                    "write_json_file",
                    side_effect=OSError("simulated metadata failure"),
                ),
            ):
                result = start_background_process(
                    command=["python", "-c", "print(1)"],
                    cwd=root,
                    log_path=root / "run.log",
                    meta_path=root / "ui_run_process.json",
                    kind="run",
                )

            self.assertIsNone(result.pid)
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with(timeout=5)
            process.kill.assert_not_called()

    def test_run_lock_reports_stale_directory_without_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            lock_path = project_dir / "active_run.json"
            lock_path.mkdir()

            acquired_path, error = acquire_run_lock(project_dir, mode="run", model_name="mock")

            self.assertIsNone(acquired_path)
            self.assertIn("Stale run lock could not be cleared", error or "")
            self.assertTrue(lock_path.is_dir())
            release_run_lock(lock_path)
            self.assertTrue(lock_path.is_dir())

    def test_run_lock_replaces_malformed_pid_without_raising(self) -> None:
        invalid_pids = (
            "not-a-pid",
            {"invalid": True},
            [123],
            None,
            True,
            1.5,
            2**63,
            "9" * 100,
        )
        for invalid_pid in invalid_pids:
            with self.subTest(pid=invalid_pid), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                lock_path = project_dir / "active_run.json"
                write_json_file(lock_path, {"pid": invalid_pid, "mode": "stale"})

                with patch.object(runtime_module, "is_pid_running") as pid_probe:
                    handle, error = acquire_run_lock(
                        project_dir,
                        mode="run",
                        model_name="mock",
                    )

                pid_probe.assert_not_called()
                self.assertIsNotNone(handle)
                self.assertIsNone(error)
                lock_data = read_json_file(lock_path)
                self.assertEqual(lock_data["pid"], os.getpid())
                self.assertEqual(lock_data["mode"], "run")
                self.assertTrue(lock_data.get("owner_token"))
                release_run_lock(handle)
                self.assertFalse(lock_path.exists())

    def test_run_lock_tolerates_corrupt_bytes_during_acquire_and_release(self) -> None:
        corrupt_payloads = (
            b"\xff",
            b'{"pid": ' + (b"9" * 5000) + b"}",
            b'{"x":' + (b"[" * 20000) + b"0" + (b"]" * 20000) + b"}",
        )
        for payload in corrupt_payloads:
            with self.subTest(payload_size=len(payload)), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                lock_path = project_dir / "active_run.json"
                lock_path.write_bytes(payload)

                handle, error = acquire_run_lock(project_dir, mode="run", model_name="mock")

                self.assertIsNotNone(handle)
                self.assertIsNone(error)
                lock_path.write_bytes(payload)
                contender, contender_error = acquire_run_lock(
                    project_dir,
                    mode="run",
                    model_name="contender",
                )
                self.assertIsNone(contender)
                self.assertIn("Another run is already active", contender_error or "")
                release_run_lock(handle)
                self.assertEqual(lock_path.read_bytes(), payload)
                retry_handle, retry_error = acquire_run_lock(
                    project_dir,
                    mode="run",
                    model_name="retry",
                )
                self.assertIsNotNone(retry_handle)
                self.assertIsNone(retry_error)
                release_run_lock(retry_handle)

    def test_run_lock_acquisition_is_exclusive_under_a_synchronized_race(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            start_barrier = threading.Barrier(3)

            def attempt(model: str) -> tuple[object, object]:
                start_barrier.wait(timeout=2)
                return acquire_run_lock(
                    project_dir,
                    mode="run",
                    model_name=model,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(attempt, model) for model in ("model-one", "model-two")]
                start_barrier.wait(timeout=2)
                results = [future.result(timeout=2) for future in futures]

            acquired = [handle for handle, error in results if handle is not None and error is None]
            blocked = [error for handle, error in results if handle is None and error is not None]
            self.assertEqual(len(acquired), 1)
            self.assertEqual(len(blocked), 1)
            self.assertIn("Another run is already active", blocked[0])
            release_run_lock(acquired[0])

    def test_run_lock_release_does_not_delete_a_replacement_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            lock_path = project_dir / "active_run.json"
            old_handle, error = acquire_run_lock(project_dir, mode="run", model_name="old")
            self.assertIsNotNone(old_handle)
            self.assertIsNone(error)
            replacement = {
                "pid": os.getpid(),
                "mode": "run",
                "model": "replacement",
                "started_at": "replacement-start",
                "owner_token": "replacement-owner",
            }
            write_json_file(lock_path, replacement)

            release_run_lock(old_handle)

            self.assertTrue(lock_path.exists())
            self.assertEqual(read_json_file(lock_path), replacement)

    def test_run_lock_bare_path_cannot_release_owner_capability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            lock_path = project_dir / "active_run.json"
            handle, error = acquire_run_lock(project_dir, mode="run", model_name="mock")
            self.assertIsNotNone(handle)
            self.assertIsNone(error)
            self.assertEqual(str(handle), str(lock_path))
            self.assertNotIn(read_json_file(lock_path)["owner_token"], repr(handle))

            release_run_lock(Path(handle))

            self.assertTrue(lock_path.exists())
            release_run_lock(handle)
            self.assertFalse(lock_path.exists())

    def test_run_lock_preserves_live_legacy_owner_and_recovers_dead_owner(self) -> None:
        for owner_live in (True, False):
            with self.subTest(owner_live=owner_live), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                lock_path = project_dir / "active_run.json"
                legacy = {
                    "pid": str(os.getpid()),
                    "mode": "legacy",
                    "model": "legacy-model",
                    "started_at": "legacy-start",
                }
                write_json_file(lock_path, legacy)

                with patch.object(
                    runtime_module,
                    "is_pid_running",
                    return_value=owner_live,
                ) as pid_probe:
                    handle, error = acquire_run_lock(
                        project_dir,
                        mode="run",
                        model_name="new-model",
                    )

                pid_probe.assert_called_once_with(os.getpid())
                if owner_live:
                    self.assertIsNone(handle)
                    self.assertIn("Another run is already active", error or "")
                    self.assertEqual(read_json_file(lock_path), legacy)
                else:
                    self.assertIsNotNone(handle)
                    self.assertIsNone(error)
                    self.assertNotEqual(read_json_file(lock_path), legacy)
                    release_run_lock(handle)

    def test_run_lock_rejects_non_regular_metadata_without_reading_it(self) -> None:
        kinds = ["symlink"]
        if hasattr(os, "mkfifo"):
            kinds.append("fifo")
        for kind in kinds:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                lock_path = project_dir / "active_run.json"
                if kind == "symlink":
                    target = project_dir / "outside-lock.json"
                    write_json_file(target, {"pid": 0, "private": "sentinel"})
                    lock_path.symlink_to(target)
                else:
                    os.mkfifo(lock_path)

                with patch.object(
                    runtime_module,
                    "read_json_file",
                    side_effect=AssertionError("non-regular lock metadata must not be read"),
                ):
                    handle, error = acquire_run_lock(
                        project_dir,
                        mode="run",
                        model_name="mock",
                    )

                self.assertIsNone(handle)
                self.assertIn("Stale run lock could not be cleared", error or "")
                self.assertTrue(lock_path.is_symlink() if kind == "symlink" else lock_path.exists())

    def test_run_lock_rejects_non_regular_guard_without_opening_it(self) -> None:
        kinds = ["symlink"]
        if hasattr(os, "mkfifo"):
            kinds.append("fifo")
        for kind in kinds:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                guard_path = project_dir / "active_run.guard"
                if kind == "symlink":
                    target = project_dir / "outside-guard"
                    target.write_bytes(b"sentinel")
                    guard_path.symlink_to(target)
                else:
                    os.mkfifo(guard_path)

                with patch.object(
                    runtime_module,
                    "_try_lock_guard",
                    side_effect=AssertionError("unsafe guard must not be opened"),
                ):
                    handle, error = acquire_run_lock(
                        project_dir,
                        mode="run",
                        model_name="mock",
                    )

                self.assertIsNone(handle)
                self.assertIn("Run lock guard could not be acquired", error or "")
                self.assertTrue(
                    guard_path.is_symlink() if kind == "symlink" else guard_path.exists()
                )

    def test_run_lock_metadata_failure_releases_guard_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)

            with patch.object(
                runtime_module,
                "write_json_file",
                side_effect=OSError("injected write failure"),
            ):
                failed_handle, error = acquire_run_lock(
                    project_dir,
                    mode="run",
                    model_name="mock",
                )

            self.assertIsNone(failed_handle)
            self.assertIn("Run lock metadata could not be written", error or "")
            retry_handle, retry_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="mock",
            )
            self.assertIsNotNone(retry_handle)
            self.assertIsNone(retry_error)
            release_run_lock(retry_handle)

    def test_run_lock_recovers_after_owner_process_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            script = (
                "import os, sys; from pathlib import Path; "
                "from src.runtime import acquire_run_lock; "
                "handle, error = acquire_run_lock(Path(sys.argv[1]), mode='run', "
                "model_name='crashed-owner'); "
                "os._exit(0 if handle is not None and error is None else 3)"
            )

            child = subprocess.run(
                [sys.executable, "-c", script, str(project_dir)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(child.returncode, 0, child.stderr)
            crashed_lock = read_json_file(project_dir / "active_run.json")
            self.assertTrue(crashed_lock.get("owner_token"))

            recovered_handle, error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="recovered-owner",
            )

            self.assertIsNotNone(recovered_handle)
            self.assertIsNone(error)
            recovered_lock = read_json_file(project_dir / "active_run.json")
            self.assertNotEqual(recovered_lock["owner_token"], crashed_lock["owner_token"])
            release_run_lock(recovered_handle)

    @unittest.skipIf(os.name == "nt", "Windows prevents unlinking an open guard")
    def test_run_lock_recreated_guard_cannot_displace_live_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            owner_handle, owner_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="owner",
            )
            self.assertIsNotNone(owner_handle)
            self.assertIsNone(owner_error)
            guard_path = project_dir / "active_run.guard"
            guard_path.unlink()

            contender, contender_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="contender",
            )

            self.assertIsNone(contender)
            self.assertIn("Another run is already active", contender_error or "")
            release_run_lock(owner_handle)
            retry_handle, retry_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="retry",
            )
            self.assertIsNotNone(retry_handle)
            self.assertIsNone(retry_error)
            release_run_lock(retry_handle)

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork semantics")
    def test_run_lock_fork_child_cannot_release_parent_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            owner_handle, owner_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="parent",
            )
            self.assertIsNotNone(owner_handle)
            self.assertIsNone(owner_error)

            child_pid = os.fork()
            if child_pid == 0:
                release_run_lock(owner_handle)
                os._exit(0)
            _, child_status = os.waitpid(child_pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(child_status), 0)
            self.assertTrue((project_dir / "active_run.json").exists())
            contender, contender_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="contender",
            )
            self.assertIsNone(contender)
            self.assertIn("Another run is already active", contender_error or "")
            release_run_lock(owner_handle)

    def test_run_lock_blocks_a_second_process_until_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ready_path = project_dir / "child-ready"
            release_path = project_dir / "release-child"
            script = """
import sys
import time
from pathlib import Path
from src.runtime import acquire_run_lock, release_run_lock

root, ready, release = map(Path, sys.argv[1:])
handle, error = acquire_run_lock(root, mode="run", model_name="child")
ready.write_text("ok" if handle is not None and error is None else "failed")
deadline = time.monotonic() + 5
while not release.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
release_run_lock(handle)
"""
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(project_dir),
                    str(ready_path),
                    str(release_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 5
            while not ready_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            try:
                self.assertTrue(ready_path.exists())
                self.assertEqual(ready_path.read_text(encoding="utf-8"), "ok")
                blocked_handle, blocked_error = acquire_run_lock(
                    project_dir,
                    mode="run",
                    model_name="parent",
                )
                self.assertIsNone(blocked_handle)
                self.assertIn("Another run is already active", blocked_error or "")
            finally:
                release_path.write_text("release", encoding="utf-8")
                stdout, stderr = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, f"{stdout}\n{stderr}")
            parent_handle, parent_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="parent",
            )
            self.assertIsNotNone(parent_handle)
            self.assertIsNone(parent_error)
            release_run_lock(parent_handle)

    def test_run_lock_simultaneous_processes_have_exactly_one_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            start_path = project_dir / "start-contenders"
            release_path = project_dir / "release-owner"
            result_paths = [project_dir / f"result-{index}" for index in range(4)]
            script = """
import sys
import time
from pathlib import Path
from src.runtime import acquire_run_lock, release_run_lock

root, start, release, result = map(Path, sys.argv[1:])
deadline = time.monotonic() + 10
while not start.exists() and time.monotonic() < deadline:
    time.sleep(0.005)
handle, error = acquire_run_lock(root, mode="run", model_name=result.name)
result.write_text("acquired" if handle is not None and error is None else "blocked")
while handle is not None and not release.exists() and time.monotonic() < deadline:
    time.sleep(0.005)
release_run_lock(handle)
"""
            children = [
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(project_dir),
                        str(start_path),
                        str(release_path),
                        str(result_path),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for result_path in result_paths
            ]
            start_path.write_text("start", encoding="utf-8")
            deadline = time.monotonic() + 10
            while not all(path.exists() for path in result_paths) and time.monotonic() < deadline:
                time.sleep(0.01)
            try:
                self.assertTrue(all(path.exists() for path in result_paths))
                results = [path.read_text(encoding="utf-8") for path in result_paths]
                self.assertEqual(results.count("acquired"), 1)
                self.assertEqual(results.count("blocked"), 3)
            finally:
                release_path.write_text("release", encoding="utf-8")
                child_outputs = [child.communicate(timeout=15) for child in children]
            for child, (stdout, stderr) in zip(children, child_outputs, strict=True):
                self.assertEqual(child.returncode, 0, f"{stdout}\n{stderr}")

    def test_run_lock_repeated_old_release_does_not_remove_new_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            lock_path = project_dir / "active_run.json"
            old_handle, old_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="old",
            )
            self.assertIsNone(old_error)
            release_run_lock(old_handle)
            new_handle, new_error = acquire_run_lock(
                project_dir,
                mode="run",
                model_name="new",
            )
            self.assertIsNone(new_error)
            new_lock = read_json_file(lock_path)

            release_run_lock(old_handle)

            self.assertEqual(read_json_file(lock_path), new_lock)
            release_run_lock(new_handle)

    def test_parse_ollama_list_output_sorts_dedupes_and_handles_empty_list(self) -> None:
        output = (
            "NAME           ID              SIZE      MODIFIED\n"
            "qwen3:8b       abc123          4.7 GB    2 days ago\n"
            "llama3.1:8b    def456          4.9 GB    yesterday\n"
            "qwen3:8b       duplicate       4.7 GB    today\n"
        )

        models = parse_ollama_list_output(output)

        self.assertEqual([model["name"] for model in models], ["llama3.1:8b", "qwen3:8b"])
        self.assertEqual(models[1]["id"], "abc123")
        self.assertEqual(parse_ollama_list_output("NAME ID SIZE MODIFIED\n"), [])

    def test_parse_ollama_tags_payload_reads_api_models(self) -> None:
        models = parse_ollama_tags_payload(
            {
                "models": [
                    {"name": "qwen3:8b", "digest": "abc", "size": 123, "modified_at": "today"},
                    {"name": "phi3:mini", "digest": "def", "size": 456},
                ]
            }
        )

        self.assertEqual([model["name"] for model in models], ["phi3:mini", "qwen3:8b"])
        self.assertEqual(models[0]["id"], "def")
        self.assertEqual(models[1]["modified"], "today")

    def test_query_ollama_models_parses_success_and_reports_missing_binary(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=(
                "NAME           ID              SIZE      MODIFIED\n"
                "qwen3:8b       abc123          4.7 GB    2 days ago\n"
                "llama3.1:8b    def456          4.9 GB    yesterday\n"
            ),
            stderr="",
        )

        with patch.object(config_module.subprocess, "run", return_value=result):
            models, error = query_ollama_models()

        self.assertIsNone(error)
        self.assertEqual([model["name"] for model in models], ["llama3.1:8b", "qwen3:8b"])
        self.assertEqual(models[1]["id"], "abc123")
        self.assertEqual(models[0]["modified"], "yesterday")

        with patch.object(config_module.subprocess, "run", return_value=result):
            names, error = list_installed_ollama_models()

        self.assertIsNone(error)
        self.assertEqual(names, ["llama3.1:8b", "qwen3:8b"])

        with (
            patch.object(config_module.subprocess, "run", side_effect=FileNotFoundError),
            patch.object(
                config_module,
                "query_ollama_api_models",
                return_value=([], "api down"),
            ),
        ):
            models, error = query_ollama_models()

        self.assertEqual(models, [])
        self.assertIn("Ollama is not installed", error or "")

    def test_query_ollama_models_falls_back_to_api_when_command_fails(self) -> None:
        result = SimpleNamespace(returncode=1, stdout="", stderr="service down")

        with (
            patch.object(config_module.subprocess, "run", return_value=result),
            patch.object(
                config_module,
                "query_ollama_api_models",
                return_value=(
                    [{"name": "phi3:mini", "id": "", "size": "", "modified": ""}],
                    None,
                ),
            ),
        ):
            models, error = query_ollama_models()

        self.assertIsNone(error)
        self.assertEqual([model["name"] for model in models], ["phi3:mini"])

    def test_query_ollama_api_error_redacts_private_endpoint(self) -> None:
        private_values = ("fixture-user", "private-token", "private-route", "query-private-token")
        endpoint = (
            "https://fixture-user:private-token@localhost:11434/"
            "private-route?key=query-private-token"
        )
        request_url = f"{endpoint}/api/tags"

        failures = (
            config_module.URLError(
                "provider-private-detail failed for /private-route?key=query-private-token/api/tags"
            ),
            InvalidURL(
                "provider-private-detail invalid /private-route?key=query-private-token/api/tags"
            ),
        )

        for failure in failures:
            with (
                self.subTest(failure=type(failure).__name__),
                patch.object(
                    config_module,
                    "urlopen",
                    side_effect=failure,
                ) as urlopen,
            ):
                models, error = config_module.query_ollama_api_models(base_url=endpoint)

            self.assertEqual(models, [])
            self.assertEqual(urlopen.call_args.args[0].full_url, request_url)
            self.assertIn("https://localhost:11434", error or "")
            for private_value in (*private_values, "provider-private-detail"):
                with self.subTest(private_value=private_value):
                    self.assertNotIn(private_value, error or "")

    def test_query_ollama_api_non_object_response_keeps_safe_failure_contract(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"[]"

        with patch.object(config_module, "urlopen", return_value=response) as urlopen:
            models, error = config_module.query_ollama_api_models(
                base_url="http://localhost:11434/proxy",
                timeout_seconds=7,
            )

        self.assertEqual(models, [])
        self.assertEqual(
            error,
            "Failed to query Ollama API at http://localhost:11434: response was not a JSON object",
        )
        self.assertEqual(
            urlopen.call_args.args[0].full_url, "http://localhost:11434/proxy/api/tags"
        )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)

    def test_query_ollama_models_drops_command_and_api_failure_text(self) -> None:
        private_values = ("fixture-user", "private-token", "private-route", "query-private-token")
        endpoint = (
            "https://fixture-user:private-token@localhost:11434/"
            "private-route?key=query-private-token"
        )
        result = SimpleNamespace(
            returncode=9,
            stdout="",
            stderr=f"command failed for {endpoint}",
        )

        with (
            patch.object(config_module.subprocess, "run", return_value=result),
            patch.object(
                config_module,
                "urlopen",
                side_effect=config_module.URLError(
                    "provider failure at /private-route?key=query-private-token/api/tags"
                ),
            ),
        ):
            models, error = query_ollama_models(base_url=endpoint)

        self.assertEqual(models, [])
        self.assertIn("ollama list failed with status 9", error or "")
        self.assertIn("https://localhost:11434", error or "")
        for private_value in private_values:
            with self.subTest(private_value=private_value):
                self.assertNotIn(private_value, error or "")

    def test_default_model_helpers_read_and_update_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"

            self.assertEqual(load_default_model_name(config_path), "qwen3:8b")
            self.assertIn(
                "config file not found",
                save_default_model_name(config_path, "qwen3:8b") or "",
            )

            config_path.write_text("model:\n  name: llama3.1:8b\n", encoding="utf-8")
            self.assertEqual(load_default_model_name(config_path), "llama3.1:8b")

            self.assertIsNone(save_default_model_name(config_path, "qwen3:14b"))
            saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["model"]["name"], "qwen3:14b")
            self.assertEqual(saved["model"]["provider"], "ollama")
            self.assertEqual(saved["model"]["timeout_seconds"], 300)

    def test_run_project_tests_reports_success_failure_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            success = SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")
            failure = SimpleNamespace(returncode=1, stdout="", stderr="failed\n")

            with patch.object(runtime_module.subprocess, "run", return_value=success) as run:
                result = run_project_tests(root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["output"], "1 passed")
            self.assertEqual(run.call_args.kwargs["cwd"], root)

            with patch.object(runtime_module.subprocess, "run", return_value=failure):
                result = run_project_tests(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["returncode"], 1)
            self.assertEqual(result["output"], "failed")

            timeout = subprocess.TimeoutExpired(
                cmd=["pytest"],
                timeout=120,
                output="partial out",
                stderr="partial err",
            )
            with patch.object(runtime_module.subprocess, "run", side_effect=timeout):
                result = run_project_tests(root)

            self.assertFalse(result["ok"])
            self.assertIsNone(result["returncode"])
            self.assertIn("partial out", result["output"])
            self.assertIn("partial err", result["output"])

    def test_streamlit_app_imports_shared_helpers(self) -> None:
        import ui.app as ui_app

        self.assertIs(ui_app.read_file_text, read_file_text)
        self.assertIs(ui_app.read_json_file, read_json_file)
        self.assertIs(ui_app.run_project_tests, run_project_tests)

    def test_ui_model_picker_prefers_manual_then_session_config_and_default(self) -> None:
        import ui.app as ui_app

        self.assertEqual(
            ui_app.resolve_effective_model(
                selected_model="qwen3:8b",
                manual_model=" phi3:mini ",
                config_model="llama3.2:3b",
            ),
            "phi3:mini",
        )
        self.assertEqual(
            ui_app.resolve_effective_model(
                selected_model="qwen3:8b",
                manual_model=" ",
                config_model="llama3.2:3b",
            ),
            "qwen3:8b",
        )

        self.assertEqual(
            ui_app.default_project_index(["example", "nebula_unique_task"], "nebula_unique_task"),
            1,
        )
        self.assertEqual(
            ui_app.default_project_index(["example", "other"], "missing_project"),
            0,
        )

    def test_ui_cloud_provider_helpers_build_safe_command_and_env(self) -> None:
        import ui.app as ui_app

        self.assertEqual(
            ui_app.resolve_effective_cloud_model(
                selected_model="gemini-2.5-flash",
                manual_model=" gemini-custom ",
                default_model="gemini-3.5-flash",
            ),
            "gemini-custom",
        )
        self.assertEqual(
            ui_app.resolve_effective_cloud_model(
                selected_model="gemini-2.5-flash",
                manual_model="",
                default_model="gemini-3.5-flash",
            ),
            "gemini-2.5-flash",
        )
        self.assertEqual(
            ui_app.provider_model_label("gemini", "gemini-3.5-flash"),
            "gemini:gemini-3.5-flash",
        )

        command = ui_app.build_run_command(
            provider="gemini",
            mode="diagnostic",
            model="gemini-3.5-flash",
            gemini_api_key_env="TEAM_GEMINI_KEY",
            project="example",
            free_runner_preset="volume_free",
            benchmark_preset="free_smoke",
            max_provider_quota_failures=2,
            drafting_mode="continue_from_previous_draft",
            gemini_api_key_override_env="AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY",
        )

        self.assertIn("--provider", command)
        self.assertIn("gemini", command)
        self.assertIn("--model", command)
        self.assertIn("gemini-3.5-flash", command)
        self.assertIn("--gemini-api-key-env", command)
        self.assertIn("TEAM_GEMINI_KEY", command)
        self.assertIn("--gemini-api-key-override-env", command)
        self.assertIn("AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY", command)
        self.assertIn("--project", command)
        self.assertIn("example", command)
        self.assertIn("--free-runner-preset", command)
        self.assertIn("volume_free", command)
        self.assertIn("--benchmark-preset", command)
        self.assertIn("free_smoke", command)
        self.assertIn("--max-provider-quota-failures", command)
        self.assertIn("2", command)
        self.assertIn("--drafting-mode", command)
        self.assertIn("continue_from_previous_draft", command)
        self.assertFalse(
            any("secret-key" in str(argument) for argument in command),
            "credential retained in generated argv",
        )
        self.assertEqual(
            ui_app.build_provider_env_overrides(
                provider="gemini",
                api_key_env="TEAM_GEMINI_KEY",
                api_key_value=" secret-key ",
            ),
            {"AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY": "secret-key"},
        )
        self.assertEqual(
            ui_app.build_provider_env_overrides(
                provider="gemini",
                api_key_env="TEAM_GEMINI_KEY",
                api_key_value="   ",
            ),
            {"AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY": ""},
        )
        self.assertEqual(
            ui_app.build_provider_env_overrides(
                provider="ollama",
                api_key_env="TEAM_GEMINI_KEY",
                api_key_value="secret-key",
            ),
            {},
        )

    def test_cloud_provider_does_not_treat_ollama_model_error_as_blocking(self) -> None:
        import ui.app as ui_app

        local_blocked = bool("Ollama is not available") or not "qwen3:8b"
        cloud_blocked = (not "gemini-3.5-flash") or (
            not ui_app.has_gemini_api_key_source(
                api_key_env="GEMINI_API_KEY",
                api_key_value="secret-key",
            )
        )

        self.assertTrue(local_blocked)
        self.assertFalse(cloud_blocked)
        self.assertEqual(
            ui_app.resolve_effective_model(
                selected_model="",
                manual_model="",
                config_model="llama3.2:3b",
            ),
            "llama3.2:3b",
        )

        installed_models = ["gemma2:2b", "qwen3:8b", "phi3:mini"]
        self.assertEqual(
            ui_app.choose_model_picker_default(
                installed_model_names=installed_models,
                session_model="phi3:mini",
                config_model="gemma2:2b",
            ),
            "phi3:mini",
        )
        self.assertEqual(
            ui_app.choose_model_picker_default(
                installed_model_names=installed_models,
                session_model="missing:latest",
                config_model="gemma2:2b",
            ),
            "gemma2:2b",
        )
        self.assertEqual(
            ui_app.choose_model_picker_default(
                installed_model_names=["gemma2:2b", "qwen3:8b"],
                session_model="missing:latest",
                config_model="missing:also",
            ),
            "qwen3:8b",
        )

    def test_ui_progress_resume_and_output_helpers(self) -> None:
        import ui.app as ui_app

        log_text = (
            "2026-05-15 12:00:00 | mode=normal | round_enter round=2\n"
            "2026-05-15 12:00:01 | mode=normal | round=2 | agent=review | status=start\n"
        )
        progress = ui_app.infer_running_stage(
            log_text=log_text,
            checkpoint={
                "last_completed_round": 1,
                "mode": "normal",
                "model": "qwen3:8b",
                "best_score": 71,
            },
            run_meta={"pid": 123, "mode": "normal", "model": "qwen3:8b"},
        )

        self.assertTrue(progress["run_active"])
        self.assertEqual(progress["stage"], "review")
        self.assertEqual(progress["round"], 2)
        self.assertEqual(ui_app.live_refresh_interval(True), "2s")
        self.assertIsNone(ui_app.live_refresh_interval(False))

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            resume = ui_app.describe_resume_state(
                project_dir=project_dir,
                checkpoint={
                    "run_id": "run1",
                    "run_root": str(run_root),
                    "can_resume": True,
                    "last_completed_round": 2,
                    "stop_reason": "USER_REQUESTED",
                    "model": "qwen3:8b",
                },
                run_active=False,
                selected_model="llama3.1:8b",
            )

        self.assertTrue(resume["can_resume"])
        self.assertIn("round 3", resume["message"])
        self.assertIn("Checkpoint model", resume["message"])
        self.assertEqual(resume["details"]["run_id"], "run1")
        self.assertEqual(resume["details"]["last_completed_round"], 2)
        self.assertEqual(resume["details"]["next_round"], 3)
        self.assertEqual(resume["details"]["stop_reason"], "USER_REQUESTED")
        self.assertTrue(resume["details"]["completed_round_files_preserved"])
        self.assertEqual(resume["details"]["next_round_status"], "missing")
        self.assertEqual(resume["details"]["next_round_safety_action"], "proceed_create_round_dir")

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            stale_resume = ui_app.describe_resume_state(
                project_dir=project_dir,
                checkpoint={
                    "run_id": "stale",
                    "run_root": str(project_dir / "runs" / "missing-run"),
                    "can_resume": True,
                    "last_completed_round": 4,
                },
                run_active=False,
                selected_model="qwen3:8b",
            )
            missing_root_resume = ui_app.describe_resume_state(
                project_dir=project_dir,
                checkpoint={"can_resume": True, "last_completed_round": 1},
                run_active=False,
                selected_model="qwen3:8b",
            )

        self.assertFalse(stale_resume["can_resume"])
        self.assertEqual(stale_resume["message_key"], "resume_stale_checkpoint")
        self.assertFalse(stale_resume["details"]["can_resume"])
        self.assertFalse(missing_root_resume["can_resume"])
        self.assertEqual(missing_root_resume["message_key"], "resume_missing_run_root")
        self.assertFalse(missing_root_resume["details"]["can_resume"])

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "partial"
            partial_round = run_root / "round_03"
            partial_round.mkdir(parents=True)
            (partial_round / "01_draft.md").write_text("partial", encoding="utf-8")
            partial_resume = ui_app.describe_resume_state(
                project_dir=project_dir,
                checkpoint={
                    "run_id": "partial",
                    "run_root": str(run_root),
                    "can_resume": True,
                    "last_completed_round": 2,
                    "stop_reason": "USER_REQUESTED",
                },
                run_active=False,
                selected_model="qwen3:8b",
            )

        self.assertFalse(partial_resume["can_resume"])
        self.assertEqual(partial_resume["message_key"], "resume_partial_next_round")
        self.assertEqual(partial_resume["details"]["next_round_status"], "partial")
        self.assertTrue(partial_resume["details"]["next_round_blocks_resume"])
        self.assertEqual(
            partial_resume["details"]["next_round_safety_action"],
            "fail_safe_require_user_action",
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            run_root = project_dir / "runs" / "run1"
            round_dir = run_root / "round_02"
            round_dir.mkdir(parents=True)
            (project_dir / "checkpoint.json").write_text("{}", encoding="utf-8")
            (round_dir / "04_judge.md").write_text("judge", encoding="utf-8")

            catalog = ui_app.build_output_catalog(
                project_dir,
                {"run_root": str(run_root), "last_completed_round": 2},
            )

        labels = [item["label"] for item in catalog]
        self.assertIn("Checkpoint", labels)
        self.assertIn("Round metrics", labels)
        self.assertIn("Latest round judge", labels)
        judge_item = next(item for item in catalog if item["label"] == "Latest round judge")
        self.assertTrue(judge_item["exists"])
        self.assertEqual(judge_item["kind"], "markdown")
        metrics_item = next(item for item in catalog if item["label"] == "Round metrics")
        self.assertEqual(metrics_item["missing_key"], "missing_round_metrics")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_live_progress_rejects_linked_project_before_automatic_reads(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            (outside_project / "checkpoint.json").write_text(
                '{"private": "SENTINEL"}\n',
                encoding="utf-8",
            )
            (outside_project / "run.log").write_text(
                "PRIVATE_LOG_SENTINEL\n",
                encoding="utf-8",
            )
            (root / "projects").symlink_to(
                root / "outside-projects",
                target_is_directory=True,
            )
            project = root / "projects" / "selected"

            with (
                patch.object(
                    ui_app,
                    "get_active_process_meta",
                    side_effect=AssertionError("metadata read must not start"),
                ) as get_meta,
                patch.object(
                    ui_app,
                    "read_json_file",
                    side_effect=AssertionError("checkpoint must not be read"),
                ) as read_checkpoint,
                patch.object(
                    ui_app,
                    "tail_file_lines",
                    side_effect=AssertionError("logs must not be read"),
                ) as read_log,
                patch.object(ui_app.st, "warning") as warning,
            ):
                ui_app.render_live_progress_and_logs(
                    proj_path=project,
                    run_log_path=project / "run.log",
                    model_job_log_path=project / "model_ops.log",
                    checkpoint_path=project / "checkpoint.json",
                    stop_signal_path=project / "STOP_REQUESTED",
                    default_model="mock",
                )

            warning.assert_called_once()
            get_meta.assert_not_called()
            read_checkpoint.assert_not_called()
            read_log.assert_not_called()

    def test_ui_disables_resume_for_unsafe_checkpoint_paths(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            project_dir.mkdir()
            outside_run = repo_root / "other" / "runs" / "run1"
            outside_run.mkdir(parents=True)

            resume = ui_app.describe_resume_state(
                project_dir=project_dir,
                checkpoint={
                    "run_id": "unsafe",
                    "run_root": str(outside_run),
                    "can_resume": True,
                    "last_completed_round": 0,
                },
                run_active=False,
                selected_model="qwen3:8b",
            )

        self.assertFalse(resume["can_resume"])
        self.assertEqual(resume["message_key"], "resume_unsafe_checkpoint")
        self.assertFalse(resume["details"]["can_resume"])
        self.assertNotIn(str(repo_root), resume["message"])

    def test_ui_score_history_rows_flatten_metrics_for_display(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            score_history_path = Path(tmp) / "score_history.json"
            score_history_path.write_text(
                """
[
  {
    "round": 1,
    "score": 82,
    "improved": true,
    "drafting_mode": "best_guided",
    "errors": [],
    "agent_timings_seconds": {"draft": 1.2, "review": 0.8, "revise": 0.7, "judge": 0.5},
    "round_runtime_seconds": 3.2,
    "estimated_input_tokens": 120,
    "estimated_output_tokens": 35,
    "estimated_total_tokens": 155,
    "evolution_metrics": {
      "score_delta_vs_previous": 4.5,
      "draft_to_revised_similarity": 0.72,
      "revised_similarity_to_previous": 0.81
    },
    "judge_rubric": {
      "evaluation_design_quality": 11,
      "tomorrow_actionability": 14
    }
  }
]
""",
                encoding="utf-8",
            )

            rows = ui_app.load_score_history_rows(score_history_path)

        self.assertEqual(rows[0]["round"], 1)
        self.assertEqual(rows[0]["score"], 82)
        self.assertEqual(rows[0]["draft_s"], 1.2)
        self.assertEqual(rows[0]["errors"], 0)
        self.assertEqual(rows[0]["estimated_input_tokens"], 120)
        self.assertEqual(rows[0]["estimated_output_tokens"], 35)
        self.assertEqual(rows[0]["estimated_total_tokens"], 155)
        self.assertEqual(rows[0]["score_delta_vs_previous"], 4.5)
        self.assertEqual(rows[0]["draft_to_revised_similarity"], 0.72)
        self.assertEqual(rows[0]["revised_similarity_to_previous"], 0.81)
        self.assertEqual(rows[0]["rubric_evaluation_design_quality"], 11)
        self.assertEqual(rows[0]["rubric_tomorrow_actionability"], 14)

    def test_ui_run_analytics_dashboard_summarizes_existing_artifacts(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            round_metrics = [
                {
                    "round": 1,
                    "score": 80.0,
                    "errors": [],
                    "agent_timings_seconds": {
                        "draft": 1.0,
                        "review": 0.5,
                        "revise": 0.4,
                        "judge": 0.3,
                    },
                    "round_runtime_seconds": 2.2,
                    "estimated_input_tokens": 100,
                    "estimated_output_tokens": 30,
                    "estimated_total_tokens": 130,
                    "evolution_metrics": {
                        "draft_to_revised_similarity": 0.72,
                    },
                    "judge_rubric": {
                        "evaluation_design_quality": 11,
                        "tomorrow_actionability": 13,
                    },
                },
                {
                    "round": 2,
                    "score": 91.0,
                    "timeout_this_round": True,
                    "errors": ["timeout"],
                    "agent_timings_seconds": {
                        "draft": 1.5,
                        "review": 0.7,
                        "revise": 0.6,
                        "judge": 0.4,
                    },
                    "round_runtime_seconds": 3.2,
                    "estimated_input_tokens": 120,
                    "estimated_output_tokens": 40,
                    "estimated_total_tokens": 160,
                    "evolution_metrics": {
                        "score_delta_vs_previous": 11,
                        "draft_to_revised_similarity": 0.75,
                        "revised_similarity_to_previous": 0.82,
                    },
                    "judge_rubric": {
                        "evaluation_design_quality": 14,
                        "tomorrow_actionability": 15,
                    },
                },
            ]
            write_json_file(
                run_root / "run_config.json",
                {
                    "run_id": "run1",
                    "model": {"provider": "ollama", "name": "qwen3:8b"},
                    "runtime": {"max_rounds": 2},
                },
            )
            write_json_file(
                run_root / "run_summary.json",
                {
                    "run_id": "run1",
                    "completed_rounds": 2,
                    "best_score": 91,
                    "timeout_count": 1,
                    "error_count": 1,
                    "total_agent_elapsed_seconds": 5.4,
                    "total_estimated_tokens": 290,
                    "round_metrics_path": str(run_root / "round_metrics.json"),
                },
            )
            (run_root / "round_metrics.json").write_text(
                json.dumps(round_metrics),
                encoding="utf-8",
            )
            (project_dir / "score_history.json").write_text(
                json.dumps(round_metrics),
                encoding="utf-8",
            )
            checkpoint = {
                "run_root": str(run_root),
                "run_summary": str(run_root / "run_summary.json"),
            }

            dashboard = ui_app.build_run_analytics_dashboard(project_dir, checkpoint)

        self.assertTrue(dashboard["available"])
        cards = {card["label_key"]: card["value"] for card in dashboard["cards"]}
        self.assertEqual(cards["analytics_best_score"], 91.0)
        self.assertEqual(cards["analytics_completed_rounds"], 2)
        self.assertEqual(cards["analytics_timeout_errors"], "1 / 1")
        self.assertEqual(cards["analytics_agent_elapsed"], "5.40s")
        self.assertEqual(cards["analytics_estimated_tokens"], 290)
        self.assertEqual(dashboard["score_rows"][-1]["score_delta"], 11)
        self.assertEqual(dashboard["rubric_rows"][-1]["evaluation"], 14.0)
        self.assertEqual(dashboard["similarity_rows"][-1]["revised_to_previous"], 0.82)
        self.assertEqual(dashboard["agent_timing_rows"][-1]["judge_s"], 0.4)
        self.assertEqual(dashboard["token_rows"][-1]["total_tokens"], 160)
        self.assertNotIn(
            str(Path(tmp)),
            "\n".join(str(value) for value in dashboard["sources"]),
        )

    def test_ui_run_analytics_dashboard_tolerates_missing_legacy_metrics(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir(parents=True)
            (project_dir / "score_history.json").write_text(
                """
[
  {"round": 1, "score": 70, "errors": [], "round_runtime_seconds": 1.5},
  {"round": 2, "score": 72, "errors": ["legacy warning"], "round_runtime_seconds": 1.7}
]
""",
                encoding="utf-8",
            )

            dashboard = ui_app.build_run_analytics_dashboard(project_dir, {})

        self.assertTrue(dashboard["available"])
        self.assertEqual(dashboard["score_rows"][-1]["score"], 72.0)
        self.assertEqual(dashboard["cards"][0]["value"], 72.0)
        self.assertEqual(dashboard["cards"][1]["value"], 2)
        self.assertEqual(dashboard["cards"][2]["value"], "0 / 1")
        self.assertEqual(dashboard["rubric_rows"], [])
        self.assertEqual(dashboard["similarity_rows"], [])

    def test_ui_run_metadata_rows_summarize_latest_run_without_absolute_paths(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            run_config_path = run_root / "run_config.json"
            run_summary_path = run_root / "run_summary.json"
            round_metrics_path = run_root / "round_metrics.json"
            write_json_file(
                run_config_path,
                {
                    "run_id": "run1",
                    "mode": "normal",
                    "drafting_mode": "continue_from_previous_draft",
                    "started_at": "2026-06-23T01:00:00+00:00",
                    "ended_at": "2026-06-23T01:02:00+00:00",
                    "stop_reason": "max_rounds",
                    "can_resume": False,
                    "completed_rounds": 2,
                    "best_score": 88.5,
                    "model": {"provider": "ollama", "name": "qwen3:8b"},
                    "runtime": {"max_rounds": 2},
                    "git": {"commit": "abcdef1234567890"},
                },
            )
            write_json_file(
                run_summary_path,
                {
                    "run_id": "run1",
                    "round_metrics_path": str(round_metrics_path),
                    "avg_revised_similarity_to_previous": 0.84,
                    "low_previous_revised_change_rounds": [2],
                    "rubric_round_count": 2,
                    "rubric_subscore_averages": {
                        "evaluation_design_quality": 12,
                    },
                },
            )
            checkpoint = {
                "run_root": str(run_root),
                "run_config": str(run_config_path),
                "run_summary": str(run_summary_path),
            }

            rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
            catalog = ui_app.build_output_catalog(project_dir, checkpoint)

        by_key = {row["field_key"]: row["value"] for row in rows}
        self.assertEqual(by_key["run_meta_provider"], "ollama")
        self.assertEqual(by_key["run_meta_model"], "qwen3:8b")
        self.assertEqual(by_key["run_meta_drafting_mode"], "continue_from_previous_draft")
        self.assertEqual(by_key["run_meta_git_commit"], "abcdef123456")
        self.assertEqual(by_key["run_meta_avg_revised_similarity"], "0.84")
        self.assertEqual(by_key["run_meta_low_change_rounds"], "1")
        self.assertEqual(by_key["run_meta_rubric_rounds"], "2")
        self.assertEqual(by_key["run_meta_rubric_avg_evaluation"], "12")
        self.assertEqual(by_key["run_meta_round_metrics_path"], "<repo>/round_metrics.json")
        self.assertNotIn(str(Path(tmp)), "\n".join(by_key.values()))

        metrics_item = next(item for item in catalog if item["label"] == "Round metrics")
        self.assertEqual(metrics_item["path"], round_metrics_path.resolve())

    def test_ui_run_artifacts_ignore_external_checkpoint_and_summary_references(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            external_dir = repo_root / "external"
            external_dir.mkdir()

            write_json_file(
                run_root / "run_config.json",
                {
                    "run_id": "run1",
                    "model": {"provider": "ollama", "name": "safe-model"},
                },
            )
            write_json_file(
                run_root / "run_summary.json",
                {
                    "run_id": "run1",
                    "best_score": 81,
                    "round_metrics_path": str(external_dir / "round_metrics.json"),
                },
            )
            write_json_file(run_root / "round_metrics.json", [{"round": 1, "score": 81}])
            write_json_file(
                external_dir / "run_config.json",
                {
                    "run_id": "private-run",
                    "model": {"provider": "EXTERNAL_PROVIDER", "name": "private-model"},
                },
            )
            write_json_file(
                external_dir / "run_summary.json",
                {
                    "run_id": "private-run",
                    "best_score": 999,
                    "round_metrics_path": str(external_dir / "round_metrics.json"),
                },
            )
            write_json_file(
                external_dir / "round_metrics.json",
                [{"round": 1, "score": 999}],
            )
            checkpoint = {
                "run_root": str(run_root),
                "run_config": str(external_dir / "run_config.json"),
                "run_summary": str(external_dir / "run_summary.json"),
                "last_completed_round": 1,
            }

            canonical_run_root = run_root.resolve()
            read_json = ui_app.read_json_file
            read_json_list = ui_app._read_json_list_file
            analyze = ui_app.analyze_run

            def guarded_read_json(path: Path) -> dict[str, object]:
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.resolve().parent, canonical_run_root)
                return read_json(path)

            def guarded_read_json_list(path: Path) -> list[dict[str, object]]:
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.resolve().parent, canonical_run_root)
                return read_json_list(path)

            def guarded_analyze(path: Path, **kwargs: object) -> dict[str, object]:
                self.assertEqual(path.resolve(), canonical_run_root)
                return analyze(path, **kwargs)

            with (
                patch.object(ui_app, "read_json_file", side_effect=guarded_read_json),
                patch.object(
                    ui_app,
                    "_read_json_list_file",
                    side_effect=guarded_read_json_list,
                ),
                patch.object(ui_app, "analyze_run", side_effect=guarded_analyze),
            ):
                rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
                dashboard = ui_app.build_run_analytics_dashboard(project_dir, checkpoint)
                catalog = ui_app.build_output_catalog(project_dir, checkpoint)

        by_key = {row["field_key"]: row["value"] for row in rows}
        self.assertEqual(by_key["run_meta_provider"], "ollama")
        self.assertEqual(by_key["run_meta_model"], "safe-model")
        self.assertEqual(dashboard["cards"][0]["value"], 81.0)
        self.assertNotIn("999", json.dumps(dashboard))
        by_label = {item["label"]: item for item in catalog}
        self.assertEqual(by_label["Run config"]["path"], run_root.resolve() / "run_config.json")
        self.assertEqual(by_label["Run summary"]["path"], run_root.resolve() / "run_summary.json")
        self.assertEqual(
            by_label["Round metrics"]["path"], run_root.resolve() / "round_metrics.json"
        )

    def test_ui_run_artifacts_do_not_read_an_external_run_root(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            project_dir.mkdir()
            outside_run = repo_root / "other" / "runs" / "private-run"
            outside_round = outside_run / "round_01"
            outside_round.mkdir(parents=True)
            write_json_file(
                outside_run / "run_config.json",
                {
                    "run_id": "private-run",
                    "model": {"provider": "EXTERNAL_PROVIDER", "name": "private-model"},
                },
            )
            (outside_round / "04_judge.md").write_text("private judge", encoding="utf-8")
            write_json_file(
                project_dir / "run_config.json",
                {
                    "run_id": "wrong-project-fallback",
                    "model": {"provider": "PROJECT_FALLBACK", "name": "wrong-model"},
                },
            )
            write_json_file(
                project_dir / "score_history.json",
                [{"round": 1, "score": 777}],
            )
            checkpoint = {
                "run_root": str(outside_run),
                "last_completed_round": 1,
            }

            with (
                patch.object(
                    ui_app,
                    "read_json_file",
                    side_effect=AssertionError("unsafe root must not be read"),
                ),
                patch.object(
                    ui_app,
                    "_read_json_list_file",
                    side_effect=AssertionError("unsafe root metrics must not be read"),
                ),
                patch.object(
                    ui_app,
                    "load_score_history_rows",
                    side_effect=AssertionError("unsafe root must not use project history"),
                ),
                patch.object(
                    ui_app,
                    "analyze_run",
                    side_effect=AssertionError("unsafe root must not be analyzed"),
                ),
            ):
                rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
                dashboard = ui_app.build_run_analytics_dashboard(project_dir, checkpoint)
                catalog = ui_app.build_output_catalog(project_dir, checkpoint)

        self.assertEqual(rows, [])
        self.assertFalse(dashboard["available"])
        self.assertNotIn("EXTERNAL_PROVIDER", json.dumps(dashboard))
        run_items = {
            item["label"]: item
            for item in catalog
            if item["label"] in {"Run config", "Run summary", "Round metrics"}
        }
        self.assertTrue(run_items)
        self.assertTrue(all(not item["exists"] for item in run_items.values()))
        self.assertTrue(all(item["path"] is None for item in run_items.values()))
        self.assertFalse(
            any(item["label"] == "Latest round judge" and item["exists"] for item in catalog)
        )

    def test_ui_selected_run_does_not_read_project_score_history(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            run_root = project_dir / "runs" / "selected-run"
            run_root.mkdir(parents=True)
            write_json_file(
                run_root / "run_config.json",
                {
                    "run_id": "selected-run",
                    "model": {"provider": "ollama", "name": "safe-model"},
                },
            )
            external_history = repo_root / "private-score-history.json"
            write_json_file(external_history, [{"round": 42, "score": 888}])
            (project_dir / "score_history.json").symlink_to(external_history)

            with patch.object(
                ui_app,
                "load_score_history_rows",
                wraps=ui_app.load_score_history_rows,
            ) as load_score_history:
                dashboard = ui_app.build_run_analytics_dashboard(
                    project_dir,
                    {"run_root": str(run_root)},
                )

        load_score_history.assert_not_called()
        self.assertFalse(dashboard["available"])
        self.assertNotIn("888", json.dumps(dashboard))
        self.assertNotIn("private-score-history", json.dumps(dashboard))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_ui_skips_linked_run_discovery_and_project_output_links(self) -> None:
        from ui import app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            runs_dir = project_dir / "runs"
            outside_run = root / "outside-run"
            runs_dir.mkdir(parents=True)
            outside_run.mkdir()
            (outside_run / "run_summary.json").write_text(
                json.dumps({"run_id": "PRIVATE_RUN", "best_score": 999}),
                encoding="utf-8",
            )
            (runs_dir / "linked-run").symlink_to(outside_run, target_is_directory=True)

            external_best = root / "external-best.md"
            external_best.write_text("PRIVATE_BEST_SENTINEL\n", encoding="utf-8")
            (project_dir / "best_output.md").symlink_to(external_best)

            self.assertEqual(ui_app.discover_project_run_roots(project_dir), [])
            catalog = ui_app.build_output_catalog(project_dir, {})
            best = next(item for item in catalog if item["label"] == "Best output")
            self.assertFalse(best["exists"])
            self.assertIsNone(best["path"])
            self.assertEqual(external_best.read_text(encoding="utf-8"), "PRIVATE_BEST_SENTINEL\n")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_ui_discovered_run_comparison_rejects_linked_metadata_leaves(self) -> None:
        from ui import app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            run_root = project_dir / "runs" / "physical-run"
            run_root.mkdir(parents=True)
            external_summary = root / "private-summary.json"
            external_summary.write_text(
                json.dumps({"run_id": "PRIVATE_RUN", "best_score": 999}),
                encoding="utf-8",
            )
            (run_root / "run_summary.json").symlink_to(external_summary)

            discovered = ui_app.discover_project_run_roots(project_dir)
            self.assertEqual([path.resolve() for path in discovered], [run_root.resolve()])
            comparison_rows = ui_app.build_run_comparison_rows(discovered)

            self.assertEqual(comparison_rows, [])
            self.assertNotIn("PRIVATE_RUN", json.dumps(comparison_rows))
            self.assertNotIn("999", json.dumps(comparison_rows))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_ui_comparison_secure_read_rejects_leaf_swap_after_preflight(self) -> None:
        from ui import app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run"
            run_root.mkdir()
            summary_path = run_root / "run_summary.json"
            summary_path.write_text(
                json.dumps({"run_id": "SAFE_RUN", "best_score": 10}),
                encoding="utf-8",
            )
            external_summary = root / "private-summary.json"
            external_summary.write_text(
                json.dumps({"run_id": "PRIVATE_RACE", "best_score": 999}),
                encoding="utf-8",
            )
            original_compare = ui_app.compare_runs

            def swap_then_compare(
                run_roots: object,
                **kwargs: object,
            ) -> dict[str, object]:
                summary_path.unlink()
                summary_path.symlink_to(external_summary)
                return original_compare(run_roots, **kwargs)

            with patch.object(
                ui_app,
                "compare_runs",
                side_effect=swap_then_compare,
            ):
                rows = ui_app.build_run_comparison_rows([run_root])

            rendered = json.dumps(rows)
            self.assertNotIn("PRIVATE_RACE", rendered)
            self.assertNotIn("999", rendered)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_ui_project_discovery_rejects_linked_projects_root(self) -> None:
        from ui import app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_projects = root / "outside-projects"
            (outside_projects / "selected").mkdir(parents=True)
            projects = root / "projects"
            projects.symlink_to(outside_projects, target_is_directory=True)

            self.assertEqual(ui_app.discover_project_names(projects), [])

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_ui_project_discovery_does_not_cross_root_swap_window(self) -> None:
        from ui import app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            (projects / "safe-name").mkdir(parents=True)
            outside_projects = root / "outside-projects"
            (outside_projects / "private-name").mkdir(parents=True)
            trusted_projects = root / "trusted-projects"
            original_lstat = Path.lstat
            swapped = False

            def lstat_then_swap(path: Path) -> os.stat_result:
                nonlocal swapped
                metadata = original_lstat(path)
                if path == projects and not swapped:
                    projects.rename(trusted_projects)
                    projects.symlink_to(outside_projects, target_is_directory=True)
                    swapped = True
                return metadata

            with patch.object(Path, "lstat", autospec=True, side_effect=lstat_then_swap):
                names = ui_app.discover_project_names(projects)

            self.assertNotIn("private-name", names)

    def test_ui_run_artifacts_reject_external_leaf_symlinks(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            outside_config = repo_root / "private-config.json"
            write_json_file(
                outside_config,
                {
                    "run_id": "private-run",
                    "model": {"provider": "EXTERNAL_PROVIDER", "name": "private-model"},
                },
            )
            (run_root / "run_config.json").symlink_to(outside_config)
            outside_round = repo_root / "private-round"
            outside_round.mkdir()
            (outside_round / "04_judge.md").write_text("private judge", encoding="utf-8")
            (run_root / "round_01").symlink_to(outside_round, target_is_directory=True)
            checkpoint = {"run_root": str(run_root), "last_completed_round": 1}

            with patch.object(ui_app, "analyze_run", wraps=ui_app.analyze_run) as analyze:
                rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
                dashboard = ui_app.build_run_analytics_dashboard(project_dir, checkpoint)
                catalog = ui_app.build_output_catalog(project_dir, checkpoint)

        self.assertNotIn("EXTERNAL_PROVIDER", json.dumps(rows))
        self.assertNotIn("EXTERNAL_PROVIDER", json.dumps(dashboard))
        analyze.assert_not_called()
        config_item = next(item for item in catalog if item["label"] == "Run config")
        self.assertFalse(config_item["exists"])
        self.assertIsNone(config_item["path"])
        self.assertFalse(
            any(item["label"] == "Latest round judge" and item["exists"] for item in catalog)
        )

    def test_ui_run_artifact_bundle_rejects_each_unsafe_leaf_before_read(self) -> None:
        import ui.app as ui_app

        cases: tuple[tuple[str, object], ...] = (
            (
                "run_config.json",
                {
                    "run_id": "private-run",
                    "model": {"provider": "PRIVATE_SENTINEL", "name": "private-model"},
                },
            ),
            ("run_summary.json", {"run_id": "private-run", "best_score": 999}),
            ("round_metrics.json", [{"round": 1, "score": 999}]),
            ("run_manifest.json", {"run_id": "private-run", "model": "PRIVATE_SENTINEL"}),
        )
        catalog_labels = {
            "run_config.json": "Run config",
            "run_summary.json": "Run summary",
            "round_metrics.json": "Round metrics",
        }

        for artifact_name, private_payload in cases:
            with self.subTest(artifact=artifact_name), tempfile.TemporaryDirectory() as tmp:
                repo_root = Path(tmp)
                project_dir = repo_root / "project"
                run_root = project_dir / "runs" / "run1"
                run_root.mkdir(parents=True)
                if artifact_name not in {"run_config.json", "run_manifest.json"}:
                    write_json_file(
                        run_root / "run_config.json",
                        {
                            "run_id": "run1",
                            "model": {"provider": "ollama", "name": "safe-model"},
                        },
                    )
                if artifact_name != "run_summary.json":
                    write_json_file(
                        run_root / "run_summary.json",
                        {"run_id": "run1", "best_score": 80},
                    )
                if artifact_name != "round_metrics.json":
                    write_json_file(
                        run_root / "round_metrics.json",
                        [{"round": 1, "score": 80}],
                    )
                private_path = repo_root / f"private-{artifact_name}"
                private_path.write_text(json.dumps(private_payload), encoding="utf-8")
                (run_root / artifact_name).symlink_to(private_path)
                checkpoint = {"run_root": str(run_root), "last_completed_round": 1}
                read_json = ui_app.read_json_file
                read_json_list = ui_app._read_json_list_file

                def guarded_read_json(path: Path) -> dict[str, object]:
                    self.assertFalse(path.is_symlink())
                    return read_json(path)

                def guarded_read_json_list(path: Path) -> list[dict[str, object]]:
                    self.assertFalse(path.is_symlink())
                    return read_json_list(path)

                with (
                    patch.object(ui_app, "read_json_file", side_effect=guarded_read_json),
                    patch.object(
                        ui_app,
                        "_read_json_list_file",
                        side_effect=guarded_read_json_list,
                    ),
                    patch.object(ui_app, "analyze_run", wraps=ui_app.analyze_run) as analyze,
                ):
                    rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
                    dashboard = ui_app.build_run_analytics_dashboard(project_dir, checkpoint)
                    catalog = ui_app.build_output_catalog(project_dir, checkpoint)

                analyze.assert_not_called()
                rendered = json.dumps({"rows": rows, "dashboard": dashboard}, default=str)
                self.assertNotIn("PRIVATE_SENTINEL", rendered)
                self.assertNotIn("999", rendered)
                if artifact_name in catalog_labels:
                    item = next(
                        item for item in catalog if item["label"] == catalog_labels[artifact_name]
                    )
                    self.assertFalse(item["exists"])
                    self.assertIsNone(item["path"])

    def test_ui_run_artifacts_reject_non_regular_leaf_and_latest_round_symlink(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            run_root = project_dir / "runs" / "run1"
            round_dir = run_root / "round_01"
            round_dir.mkdir(parents=True)
            write_json_file(
                run_root / "run_config.json",
                {"run_id": "run1", "model": {"provider": "ollama", "name": "safe-model"}},
            )
            (run_root / "run_summary.json").mkdir()
            private_judge = repo_root / "private-judge.md"
            private_judge.write_text("PRIVATE_JUDGE", encoding="utf-8")
            (round_dir / "04_judge.md").symlink_to(private_judge)
            checkpoint = {"run_root": str(run_root), "last_completed_round": 1}

            with patch.object(ui_app, "analyze_run", wraps=ui_app.analyze_run) as analyze:
                rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
                catalog = ui_app.build_output_catalog(project_dir, checkpoint)

        analyze.assert_not_called()
        by_key = {row["field_key"]: row["value"] for row in rows}
        self.assertEqual(by_key["run_meta_provider"], "ollama")
        self.assertEqual(by_key["run_meta_run_summary_path"], "N/A")
        summary_item = next(item for item in catalog if item["label"] == "Run summary")
        judge_item = next(item for item in catalog if item["label"] == "Latest round judge")
        self.assertFalse(summary_item["exists"])
        self.assertIsNone(summary_item["path"])
        self.assertFalse(judge_item["exists"])
        self.assertIsNone(judge_item["path"])

    def test_ui_run_artifacts_support_configured_runs_storage_symlink_read_only(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            project_dir.mkdir()
            runs_storage = repo_root / "configured-runs-storage"
            runs_storage.mkdir()
            (project_dir / "runs").symlink_to(runs_storage, target_is_directory=True)
            run_root = runs_storage / "run1"
            run_root.mkdir()
            write_json_file(
                run_root / "run_config.json",
                {
                    "run_id": "run1",
                    "model": {"provider": "ollama", "name": "safe-model"},
                },
            )
            root_access_modes: list[int] = []

            def read_only_access(path: object, mode: int) -> bool:
                if Path(path).resolve() == run_root.resolve():
                    root_access_modes.append(mode)
                    return not bool(mode & os.W_OK)
                return True

            with patch("src.resume_safety.os.access", side_effect=read_only_access):
                rows = ui_app.build_run_metadata_rows(
                    project_dir,
                    {"run_root": str(project_dir / "runs" / "run1")},
                )

        by_key = {row["field_key"]: row["value"] for row in rows}
        self.assertEqual(by_key["run_meta_provider"], "ollama")
        self.assertTrue(root_access_modes)
        self.assertTrue(all(not mode & os.W_OK for mode in root_access_modes))

    def test_stop_signal_display_path_is_masked(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            stop_signal_path = Path(tmp) / "project" / "STOP_REQUESTED"

            display_path = ui_app.output_display_path(stop_signal_path)

        self.assertEqual(display_path, "<repo>/STOP_REQUESTED")
        self.assertNotIn(str(Path(tmp)), display_path)

    def test_create_stop_signal_tolerates_stale_directory_path(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            stop_signal_path = Path(tmp) / "project" / "STOP_REQUESTED"
            stop_signal_path.mkdir(parents=True)

            self.assertFalse(ui_app.create_stop_signal(stop_signal_path))
            display_path = ui_app.output_display_path(stop_signal_path)

        self.assertEqual(display_path, "<repo>/STOP_REQUESTED")
        self.assertNotIn(str(Path(tmp)), display_path)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_create_stop_signal_rejects_linked_project_ancestor(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            (root / "projects").symlink_to(
                root / "outside-projects",
                target_is_directory=True,
            )
            stop_path = root / "projects" / "selected" / "STOP_REQUESTED"

            self.assertFalse(ui_app.create_stop_signal(stop_path))
            self.assertFalse((outside_project / "STOP_REQUESTED").exists())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_stop_requested_rejects_external_marker_after_project_ancestor_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project = projects / "selected"
            project.mkdir(parents=True)
            trusted_projects = root / "trusted-projects"
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            (outside_project / "STOP_REQUESTED").write_text("stop\n", encoding="utf-8")
            ensure_project_runtime_paths_safe(project)
            projects.rename(trusted_projects)
            projects.symlink_to(root / "outside-projects", target_is_directory=True)

            self.assertFalse(stop_requested(project / "STOP_REQUESTED"))

    def test_ui_run_comparison_helpers_mask_paths_and_flatten_fields(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_a = project_dir / "runs" / "run-a"
            run_b = project_dir / "runs" / "run-b"
            run_a.mkdir(parents=True)
            run_b.mkdir(parents=True)
            write_json_file(
                run_a / "run_config.json",
                {
                    "run_id": "run-a",
                    "drafting_mode": "best_guided",
                    "model": {"provider": "ollama", "name": "qwen3:8b"},
                    "runtime": {"max_rounds": 2},
                },
            )
            write_json_file(
                run_a / "round_metrics.json",
                [
                    {
                        "round": 1,
                        "score": 60.0,
                        "timeout_this_round": True,
                        "agent_timings_seconds": {"draft": 1.0},
                        "estimated_input_tokens": 10,
                        "estimated_output_tokens": 5,
                        "estimated_total_tokens": 15,
                    },
                    {
                        "round": 2,
                        "score": 70.0,
                        "errors": ["boom"],
                        "agent_timings_seconds": {"draft": 2.0},
                        "estimated_input_tokens": 20,
                        "estimated_output_tokens": 5,
                        "estimated_total_tokens": 25,
                        "evolution_metrics": {
                            "draft_to_revised_similarity": 0.6,
                            "revised_similarity_to_previous": 0.97,
                        },
                        "judge_rubric": {
                            "evaluation_design_quality": 13,
                            "tomorrow_actionability": 16,
                        },
                    },
                ],
            )
            write_json_file(
                run_b / "run_summary.json",
                {
                    "run_id": "run-b",
                    "model": "gemini-3.5-flash",
                    "drafting_mode": "fresh_from_task_with_review",
                    "best_score": 88.0,
                    "completed_rounds": 1,
                },
            )

            discovered = ui_app.discover_project_run_roots(project_dir)
            rows = ui_app.build_run_comparison_rows([run_a, run_b])

        self.assertEqual({path.name for path in discovered}, {"run-a", "run-b"})
        by_id = {row["run_id"]: row for row in rows}
        self.assertEqual(by_id["run-a"]["provider"], "ollama")
        self.assertEqual(by_id["run-a"]["model"], "qwen3:8b")
        self.assertEqual(by_id["run-a"]["max_rounds"], "2")
        self.assertEqual(by_id["run-a"]["average_score"], 65.0)
        self.assertEqual(by_id["run-a"]["timeout_count"], "1")
        self.assertEqual(by_id["run-a"]["error_count"], "1")
        self.assertEqual(by_id["run-a"]["agent_elapsed_s"], "3.0")
        self.assertEqual(by_id["run-a"]["estimated_tokens"], "40")
        self.assertEqual(by_id["run-a"]["avg_revised_similarity"], "0.97")
        self.assertEqual(by_id["run-a"]["low_change_rounds"], "1")
        self.assertEqual(by_id["run-a"]["rubric_rounds"], "1")
        self.assertEqual(by_id["run-a"]["rubric_avg_evaluation"], "13.0")
        self.assertEqual(by_id["run-a"]["rubric_avg_actionability"], "16.0")
        self.assertEqual(by_id["run-a"]["run_path"], "<repo>/run-a")
        self.assertNotIn(
            str(Path(tmp)), "\n".join(str(value) for row in rows for value in row.values())
        )

    def test_fast_model_health_check_uses_api_and_selected_model_presence(self) -> None:
        import ui.app as ui_app

        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"models": [{"name": "qwen3:8b"}]},
        )

        with patch.object(ui_app.requests, "get", return_value=response) as get:
            health = ui_app.check_model_health(
                base_url="http://localhost:11434",
                selected_model="qwen3:8b",
                installed_model_names=[],
            )

        self.assertTrue(health["ok"])
        self.assertTrue(health["api_ok"])
        self.assertTrue(health["model_ok"])
        self.assertEqual(get.call_args.args[0], "http://localhost:11434/api/tags")

        with patch.object(ui_app.requests, "get", return_value=response):
            health = ui_app.check_model_health(
                base_url="http://localhost:11434",
                selected_model="missing:latest",
                installed_model_names=[],
            )

        self.assertFalse(health["ok"])
        self.assertTrue(health["api_ok"])
        self.assertFalse(health["model_ok"])
        self.assertIn("not installed", health["message"])

        private_endpoint = "https://user:private-token@localhost:11434/proxy?key=private-token"
        with patch.object(
            ui_app.requests,
            "get",
            side_effect=ui_app.requests.ConnectionError(f"request failed for {private_endpoint}"),
        ):
            health = ui_app.check_model_health(
                base_url=private_endpoint,
                selected_model="qwen3:8b",
                installed_model_names=[],
            )

        self.assertFalse(health["ok"])
        self.assertNotIn("private-token", repr(health))
        self.assertIn("https://localhost:11434", health["message"])

    def test_ollama_health_rejects_non_mapping_json_responses(self) -> None:
        import ui.app as ui_app

        expected = {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": ("Ollama API is not healthy at https://localhost:11434: InvalidResponse"),
            "message_key": "health_api_unhealthy",
            "message_args": {
                "base_url": "https://localhost:11434",
                "error": "InvalidResponse",
            },
        }
        response_shapes = (
            [],
            "provider-controlled-detail",
            42,
            True,
            False,
            None,
        )
        private_endpoint = "https://fixture-user:private-token@localhost:11434/proxy/"

        for payload in response_shapes:
            with self.subTest(payload=payload):
                response = SimpleNamespace(
                    raise_for_status=lambda: None,
                    json=lambda payload=payload: payload,
                )
                with patch.object(ui_app.requests, "get", return_value=response) as get:
                    health = ui_app.check_ollama_model_health(
                        base_url=private_endpoint,
                        selected_model="qwen3:8b",
                        installed_model_names=[],
                        timeout_seconds=7,
                    )

                self.assertEqual(health, expected)
                get.assert_called_once_with(
                    f"{private_endpoint}api/tags",
                    timeout=7,
                )
                self.assertNotIn("provider-controlled-detail", repr(health))
                self.assertNotIn("private-token", repr(health))

        empty_object_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {},
        )
        with patch.object(
            ui_app.requests,
            "get",
            return_value=empty_object_response,
        ) as get:
            health = ui_app.check_ollama_model_health(
                base_url=private_endpoint,
                selected_model="qwen3:8b",
                installed_model_names=[],
                timeout_seconds=7,
            )

        self.assertFalse(health["ok"])
        self.assertTrue(health["api_ok"])
        self.assertFalse(health["model_ok"])
        self.assertEqual(health["message_key"], "health_model_missing")
        self.assertEqual(health["message_args"], {"model": "qwen3:8b"})
        get.assert_called_once_with(f"{private_endpoint}api/tags", timeout=7)
        self.assertNotIn("private-token", repr(health))

    def test_ui_ollama_private_path_scope_avoids_equal_length_collisions(self) -> None:
        import ui.app as ui_app

        private_path_pairs = (
            ("/alpha", "/bravo"),
            ("/alpha/charlie", "/bravo/foxtrot"),
            ("/alpha/bravo", "/bravo/alpha"),
        )
        for first_path, second_path in private_path_pairs:
            with self.subTest(first_path=first_path, second_path=second_path):
                first_scope = ui_app.ollama_health_connection_scope(f"http://localhost{first_path}")
                second_scope = ui_app.ollama_health_connection_scope(
                    f"http://localhost{second_path}"
                )
                self.assertNotEqual(first_scope, second_scope)

        self.assertEqual(
            ui_app.ollama_health_connection_scope(" HTTP://LOCALHOST:80/alpha/ "),
            ui_app.ollama_health_connection_scope("http://localhost/alpha"),
        )

    def test_ui_ollama_private_path_change_evicts_cached_health_result(self) -> None:
        import ui.app as ui_app

        session_state: dict[str, object] = {}
        first_identity = ui_app.build_model_health_identity(
            provider="ollama",
            model="qwen3:8b",
            connection_scope=ui_app.ollama_health_connection_scope("http://localhost/alpha"),
        )
        second_identity = ui_app.build_model_health_identity(
            provider="ollama",
            model="qwen3:8b",
            connection_scope=ui_app.ollama_health_connection_scope("http://localhost/bravo"),
        )
        result = {
            "ok": True,
            "message": "healthy",
            "message_key": "health_model_ok",
            "message_args": {"model": "qwen3:8b"},
        }

        ui_app.store_scoped_health_result(
            session_state,
            key="model_health",
            identity=first_identity,
            result=result,
        )
        self.assertEqual(
            ui_app.load_scoped_health_result(
                session_state,
                key="model_health",
                identity=first_identity,
            ),
            result,
        )
        self.assertIsNone(
            ui_app.load_scoped_health_result(
                session_state,
                key="model_health",
                identity=second_identity,
            )
        )
        self.assertNotIn("model_health", session_state)

    def test_ui_ollama_private_path_scope_is_opaque_and_preserves_presence(self) -> None:
        import base64
        import hashlib

        import src.ui_health_identity as health_identity
        import ui.app as ui_app

        private_path = "/private-%E2%98%83-alpha"
        first_url = (
            f"https://first-user:first-password@localhost{private_path}"
            "?token=first-query#first-fragment"
        )
        rotated_url = (
            f"https://second-user:second-password@localhost{private_path}"
            "?token=second-query#second-fragment"
        )
        fixed_key = b"K" * 32
        with patch.object(health_identity, "_PRIVATE_PATH_ID_KEY", fixed_key):
            first_scope = ui_app.ollama_health_connection_scope(first_url)
            rotated_scope = ui_app.ollama_health_connection_scope(rotated_url)
            no_userinfo_scope = ui_app.ollama_health_connection_scope(
                f"https://localhost{private_path}?token=first-query"
            )
            no_query_scope = ui_app.ollama_health_connection_scope(
                f"https://first-user:first-password@localhost{private_path}"
            )

        self.assertEqual(first_scope, rotated_scope)
        self.assertNotEqual(first_scope, no_userinfo_scope)
        self.assertNotEqual(first_scope, no_query_scope)
        self.assertEqual(first_scope[4], "private_path_id")
        self.assertEqual(len(first_scope[5]), 64)

        serialized_scope = repr(first_scope)
        reversible_values = (
            private_path,
            private_path.encode("utf-8").hex(),
            base64.b64encode(private_path.encode("utf-8")).decode("ascii"),
            base64.urlsafe_b64encode(private_path.encode("utf-8")).decode("ascii"),
            hashlib.sha256(private_path.encode("utf-8")).hexdigest(),
            fixed_key.hex(),
            base64.b64encode(fixed_key).decode("ascii"),
            "first-user",
            "first-password",
            "first-query",
            "first-fragment",
        )
        for value in reversible_values:
            with self.subTest(value=value):
                self.assertNotIn(value, serialized_scope)

        self.assertEqual(
            ui_app.ollama_health_connection_scope("http://localhost/api/v1"),
            (
                "endpoint",
                "http",
                "localhost",
                "80",
                "path",
                "/api/v1",
                "anonymous",
                "no_query",
            ),
        )

    def test_ui_ollama_private_path_identity_is_process_scoped(self) -> None:
        import importlib

        import src.ui_health_identity as health_identity
        import ui.app as ui_app

        private_url = "http://localhost/private-alpha"
        safe_url = "http://localhost/proxy"
        before_reload = ui_app.ollama_health_connection_scope(private_url)
        self.assertEqual(
            importlib.reload(ui_app).ollama_health_connection_scope(private_url),
            before_reload,
        )

        with patch.object(health_identity, "_PRIVATE_PATH_ID_KEY", b"A" * 32):
            private_scope_a = ui_app.ollama_health_connection_scope(private_url)
            safe_scope_a = ui_app.ollama_health_connection_scope(safe_url)
        with patch.object(health_identity, "_PRIVATE_PATH_ID_KEY", b"B" * 32):
            private_scope_b = ui_app.ollama_health_connection_scope(private_url)
            safe_scope_b = ui_app.ollama_health_connection_scope(safe_url)

        self.assertNotEqual(private_scope_a, private_scope_b)
        self.assertEqual(safe_scope_a, safe_scope_b)

    def test_ui_health_session_result_is_scoped_to_checked_target(self) -> None:
        import ui.app as ui_app

        session_state: dict[str, object] = {"model_health": {"ok": True}}
        ollama_scope = ui_app.ollama_health_connection_scope(
            "https://user:private-token@LOCALHOST:11434/proxy/?token=private-token"
        )
        ollama_identity = ui_app.build_model_health_identity(
            provider="ollama",
            model=" qwen3:8b ",
            connection_scope=ollama_scope,
        )
        self.assertNotIn("private-token", repr(ollama_identity))
        self.assertNotIn(
            "sk_live_abc123",
            repr(ui_app.ollama_health_connection_scope("https://localhost/sk_live_abc123")),
        )
        self.assertEqual(
            ui_app.ollama_health_connection_scope("http://LOCALHOST:80/"),
            ui_app.ollama_health_connection_scope("http://localhost"),
        )
        self.assertNotEqual(
            ui_app.ollama_health_connection_scope("http://localhost/proxy"),
            ui_app.ollama_health_connection_scope("http://localhost/api"),
        )
        self.assertNotEqual(
            ui_app.ollama_health_connection_scope("http://localhost:99999"),
            ui_app.ollama_health_connection_scope("http://localhost:99998"),
        )
        self.assertNotIn(
            "private-token",
            repr(ui_app.ollama_health_connection_scope("http://localhost:private-token")),
        )
        self.assertEqual(
            ui_app.build_model_health_identity(
                provider=" OLLAMA ",
                model="qwen3:8b",
                connection_scope=ollama_scope,
            ),
            ollama_identity,
        )
        self.assertIsNone(
            ui_app.load_scoped_health_result(
                session_state,
                key="model_health",
                identity=ollama_identity,
            )
        )
        self.assertNotIn("model_health", session_state)

        result = {
            "ok": False,
            "message": "model was not installed",
            "message_key": "health_model_missing",
            "message_args": {"model": "qwen3:8b"},
        }
        ui_app.store_scoped_health_result(
            session_state,
            key="model_health",
            identity=ollama_identity,
            result=result,
        )
        self.assertEqual(
            ui_app.load_scoped_health_result(
                session_state,
                key="model_health",
                identity=ollama_identity,
            ),
            result,
        )
        self.assertNotIn("private-token", repr(session_state))

        changed_identities = (
            ui_app.build_model_health_identity(
                provider="ollama",
                model="qwen3:14b",
                connection_scope=ollama_scope,
            ),
            ui_app.build_model_health_identity(
                provider="ollama",
                model="qwen3:8b",
                connection_scope=ui_app.ollama_health_connection_scope("http://localhost:11435"),
            ),
            ui_app.build_model_health_identity(
                provider="gemini",
                model="qwen3:8b",
                connection_scope=ollama_scope,
            ),
        )
        for changed_identity in changed_identities:
            with self.subTest(changed_identity=changed_identity):
                ui_app.store_scoped_health_result(
                    session_state,
                    key="model_health",
                    identity=ollama_identity,
                    result=result,
                )
                self.assertIsNone(
                    ui_app.load_scoped_health_result(
                        session_state,
                        key="model_health",
                        identity=changed_identity,
                    )
                )
                self.assertNotIn("model_health", session_state)

        self.assertEqual(
            ui_app.resolve_ui_gemini_api_key("   ", " config-key "),
            "config-key",
        )
        custom_environment = {
            "TEAM_KEY": "private-custom-key",
            "GOOGLE_API_KEY": "private-google-key",
            "GEMINI_API_KEY": "private-gemini-key",
        }
        custom_scope = ui_app.gemini_health_connection_scope(
            api_key_env="TEAM_KEY",
            session_key_present=False,
            config_key_present=False,
            environment=custom_environment,
        )
        google_scope = ui_app.gemini_health_connection_scope(
            api_key_env="GEMINI_API_KEY",
            session_key_present=False,
            config_key_present=False,
            environment=custom_environment,
        )
        gemini_scope = ui_app.gemini_health_connection_scope(
            api_key_env="GEMINI_API_KEY",
            session_key_present=False,
            config_key_present=False,
            environment={"GEMINI_API_KEY": "private-gemini-key"},
        )
        whitespace_google_scope = ui_app.gemini_health_connection_scope(
            api_key_env="GEMINI_API_KEY",
            session_key_present=False,
            config_key_present=False,
            environment={"GOOGLE_API_KEY": "   ", "GEMINI_API_KEY": "private-gemini-key"},
        )
        session_scope = ui_app.gemini_health_connection_scope(
            api_key_env="TEAM_KEY",
            session_key_present=True,
            config_key_present=True,
            environment=custom_environment,
        )
        config_scope = ui_app.gemini_health_connection_scope(
            api_key_env="TEAM_KEY",
            session_key_present=False,
            config_key_present=True,
            environment=custom_environment,
        )
        self.assertEqual(custom_scope, ("environment", "TEAM_KEY"))
        self.assertEqual(google_scope, ("environment", "GOOGLE_API_KEY"))
        self.assertEqual(gemini_scope, ("environment", "GEMINI_API_KEY"))
        self.assertEqual(whitespace_google_scope, ("environment", "GOOGLE_API_KEY"))
        self.assertEqual(session_scope, ("session_key",))
        self.assertEqual(config_scope, ("config_key",))
        self.assertNotIn("private-", repr((custom_scope, google_scope, gemini_scope)))

        gemini_environment_identity = ui_app.build_model_health_identity(
            provider="gemini",
            model="gemini-3.5-flash",
            connection_scope=google_scope,
        )
        gemini_config_identity = ui_app.build_model_health_identity(
            provider="gemini",
            model="gemini-3.5-flash",
            connection_scope=config_scope,
        )
        ui_app.store_scoped_health_result(
            session_state,
            key="gemini_model_health",
            identity=gemini_environment_identity,
            result={
                "ok": True,
                "message": "healthy",
                "message_key": "gemini_health_ok",
                "message_args": {"model": "gemini-3.5-flash"},
            },
        )
        self.assertIsNone(
            ui_app.load_scoped_health_result(
                session_state,
                key="gemini_model_health",
                identity=gemini_config_identity,
            )
        )
        self.assertNotIn("gemini_model_health", session_state)

        malformed_entries: tuple[object, ...] = (
            ["not a mapping"],
            {"ok": True},
            {
                "identity": ollama_identity,
                "result": {
                    "ok": 1,
                    "message": "bad ok",
                    "message_key": "health_model_ok",
                    "message_args": {},
                },
            },
            {
                "identity": ollama_identity,
                "result": {
                    "ok": True,
                    "message": "bad args",
                    "message_key": "health_model_ok",
                    "message_args": None,
                },
            },
            {
                "identity": ollama_identity,
                "result": {
                    "ok": True,
                    "message": "missing format argument",
                    "message_key": "health_model_ok",
                    "message_args": {},
                },
            },
        )
        for malformed in malformed_entries:
            with self.subTest(malformed=malformed):
                session_state["model_health"] = malformed
                self.assertIsNone(
                    ui_app.load_scoped_health_result(
                        session_state,
                        key="model_health",
                        identity=ollama_identity,
                    )
                )
                self.assertNotIn("model_health", session_state)

    def test_gemini_health_check_uses_mocked_client_and_missing_key_short_circuits(self) -> None:
        import ui.app as ui_app

        with patch.object(ui_app, "has_gemini_api_key_source", return_value=False):
            health = ui_app.check_gemini_model_health(
                selected_model="gemini-3.5-flash",
                api_key_env="GEMINI_API_KEY",
            )

        self.assertFalse(health["ok"])
        self.assertEqual(health["message_key"], "gemini_health_missing_key")

        with (
            patch.object(ui_app, "has_gemini_api_key_source", return_value=True),
            patch.object(
                ui_app.GeminiClient,
                "generate",
                return_value="OK",
            ) as generate,
        ):
            health = ui_app.check_gemini_model_health(
                selected_model="gemini-3.5-flash",
                api_key_env="GEMINI_API_KEY",
                api_key_value="secret-key",
            )

        self.assertTrue(health["ok"])
        self.assertEqual(health["message_key"], "gemini_health_ok")
        generate.assert_called_once()

        with (
            patch.object(ui_app, "has_gemini_api_key_source", return_value=True),
            patch.object(
                ui_app.GeminiClient,
                "generate",
                side_effect=RuntimeError("private-key-from-provider"),
            ),
        ):
            health = ui_app.check_gemini_model_health(
                selected_model="gemini-3.5-flash",
                api_key_env="GEMINI_API_KEY",
                api_key_value="secret-key",
            )

        self.assertFalse(health["ok"])
        self.assertNotIn("private-key-from-provider", repr(health))


if __name__ == "__main__":
    unittest.main()

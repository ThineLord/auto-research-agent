"""Loopback-only dashboard server. Reuses the established safe research operations."""

from __future__ import annotations

import argparse
import dataclasses
import json
import mimetypes
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ui import app as h
from ui.i18n import TRANSLATIONS

WEB = Path(__file__).with_name("web")
TOKEN = secrets.token_urlsafe(32)
ACTION_LOCK = threading.Lock()


def project(name: str) -> Path:
    if name not in h.discover_project_names(h.PROJECTS_DIR):
        raise ValueError("Unknown project")
    path = h.PROJECTS_DIR / name
    h.ensure_project_runtime_paths_safe(path, anchor=h.PROJECTS_DIR)
    return path


def config_public() -> dict:
    config, example = h.load_ui_config()
    return {
        "provider": config.model.provider,
        "model": config.model.name,
        "cloud_models": config.model.gemini.models,
        "api_key_env": config.model.gemini.api_key_env,
        "key_available": h.has_gemini_api_key_source(
            api_key_env=config.model.gemini.api_key_env,
            config_api_key=config.model.gemini.api_key,
        ),
        "drafting_mode": config.drafting_mode,
        "free_runner_preset": config.cloud_free.free_runner_preset,
        "project": config.project_name,
        "example": example,
    }


def status(name: str, model: str = "") -> dict:
    path = project(name)
    checkpoint = h.read_json_file(path / "checkpoint.json")
    meta = h.get_active_process_meta(h.run_meta_path(path))
    log = h.tail_file_lines(path / "run.log", 120)
    return {
        "progress": h.infer_running_stage(log_text=log, checkpoint=checkpoint, run_meta=meta),
        "resume": h.describe_resume_state(
            project_dir=path, checkpoint=checkpoint, run_active=bool(meta), selected_model=model
        ),
        "model_job": h.get_active_process_meta(h.model_job_meta_path(path)),
        "log": log,
        "model_log": h.tail_file_lines(path / "model_ops.log", 80),
        "stop_requested": h.artifact_path_exists(path / "STOP_REQUESTED"),
    }


def workspace(name: str) -> dict:
    path = project(name)
    checkpoint = h.read_json_file(path / "checkpoint.json")
    catalog = h.build_output_catalog(path, checkpoint)
    config, _ = h.load_ui_config()
    return {
        **status(name),
        "task": h.read_file_text(path / "task.md"),
        "memory": h.read_file_text(path / "memory.md"),
        "recommendations": {
            preset: cloud_pool(path, config, preset)["recommendation"]
            for preset in h.FREE_RUNNER_PRESETS
        },
        "outputs": [
            {
                "id": i,
                "label_key": row["label_key"],
                "exists": row["exists"],
                "kind": row["kind"],
                "path": h.output_display_path(row["path"]) if row["path"] is not None else "",
            }
            for i, row in enumerate(catalog)
        ],
    }


def output(name: str, index: int) -> dict:
    path = project(name)
    catalog = h.build_output_catalog(path, h.read_json_file(path / "checkpoint.json"))
    if index < 0 or index >= len(catalog):
        raise ValueError("Unknown output")
    row = catalog[index]
    if not row["exists"] or row["path"] is None:
        return {"content": "", "exists": False}
    return {"content": h.read_regular_text(row["path"], missing_ok=False), "exists": True}


def analytics(name: str) -> dict:
    path = project(name)
    checkpoint = h.read_json_file(path / "checkpoint.json")
    return {
        **h.build_run_analytics_dashboard(path, checkpoint),
        "metadata": h.build_run_metadata_rows(path, checkpoint),
        "comparison": h.build_run_comparison_rows(
            h.discover_project_run_roots(path), project_dir=path
        ),
    }


def model_name(value: object) -> str:
    name = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}", name):
        raise ValueError("Invalid model name")
    return name


def selection(data: dict) -> tuple:
    config, _ = h.load_ui_config()
    provider = data.get("provider", config.model.provider)
    if provider not in h.SUPPORTED_MODEL_PROVIDERS:
        raise ValueError("Invalid provider")
    model = model_name(data.get("model", config.model.name))
    env = str(data.get("api_key_env", config.model.gemini.api_key_env)).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
        raise ValueError("Invalid environment variable")
    key = str(data.get("api_key", "")).strip()
    return config, provider, model, env, key


def cloud_pool(path: Path, config, preset: str) -> dict:
    discovered = h.load_discovery_artifact(path)
    profiles = h.load_profile_artifact(path)
    candidates = h.build_cached_candidate_pool(
        discovered_models=discovered,
        configured_models=config.model.gemini.models,
        profiles=profiles,
        config=config.cloud_free,
    )
    recommendation = h.recommend_free_cloud_model(
        candidates=candidates, profiles=profiles, preset=preset
    )
    return {"candidates": candidates, "profiles": profiles, "recommendation": recommendation}


def action(data: dict) -> dict:
    path = project(str(data.get("project", "")))
    operation = data.get("action")
    if operation == "save":
        if not isinstance(data.get("task"), str) or not isinstance(data.get("memory"), str):
            raise ValueError("Invalid input")
        h.ensure_artifact_paths_safe((path / "task.md", path / "memory.md"))
        h.write_file_text(path / "task.md", data["task"])
        h.write_file_text(path / "memory.md", data["memory"])
        return {"message_key": "input_saved"}
    active = h.get_active_process_meta(h.run_meta_path(path))
    job = h.get_active_process_meta(h.model_job_meta_path(path))
    if operation == "stop":
        if not active:
            raise ValueError("No active run")
        if not h.create_stop_signal(path / "STOP_REQUESTED"):
            raise OSError("Could not request a safe stop")
        return {"message_key": "stop_signal_created", "message_args": {"path": "STOP_REQUESTED"}}
    if operation == "tests":
        if active:
            raise ValueError("A research run is active")
        return h.run_project_tests(h.ROOT)
    config, provider, model, env, key = selection(data)
    if operation == "models":
        models, error = h.query_ollama_models(base_url=config.ollama_base_url, timeout_seconds=5)
        return {"models": models, "error": error}
    if operation == "health":
        if provider == "gemini":
            return h.check_gemini_model_health(
                selected_model=model,
                api_key_env=env,
                api_key_value=key or config.model.gemini.api_key,
            )
        models, _ = h.query_ollama_models(base_url=config.ollama_base_url, timeout_seconds=5)
        return h.check_model_health(
            provider=provider,
            base_url=config.ollama_base_url,
            selected_model=model,
            installed_model_names=[m["name"] for m in models],
        )
    if operation == "default":
        error = h.save_default_model_selection(
            h.CONFIG_PATH, provider=provider, model_name=model, gemini_api_key_env=env
        )
        if error:
            raise ValueError(error)
        return {"message_key": "saved_default_model", "message_args": {"model": model}}
    if operation in {"cloud", "discover", "profile"}:
        preset = data.get("free_runner_preset", config.cloud_free.free_runner_preset)
        if preset not in h.FREE_RUNNER_PRESETS:
            raise ValueError("Invalid preset")
        if operation == "discover":
            discovered, error = h.discover_free_cloud_models(
                api_key_env=env,
                api_key=key or config.model.gemini.api_key,
                config=config.cloud_free,
            )
            if error:
                raise ValueError(error)
            h.save_discovery_artifact(path, discovered)
        elif operation == "profile":
            candidates = h.build_candidate_pool(
                discovered_models=h.load_discovery_artifact(path),
                configured_models=config.model.gemini.models,
                config=config.cloud_free,
            )
            profiles = h.profile_free_cloud_models(
                candidates=h.filter_safe_text_models(candidates, include_unavailable=True),
                api_key_env=env,
                api_key=key or config.model.gemini.api_key,
            )
            h.save_profile_artifact(path, profiles)
        return cloud_pool(path, config, preset)
    if active or (job and (operation in {"pull", "delete"} or provider == "ollama")):
        raise ValueError("A run or model operation is active")
    if operation in {"pull", "delete"}:
        target = model_name(data.get("target"))
        if operation == "delete":
            if data.get("confirmation") != target:
                raise ValueError("Model deletion requires its exact name as confirmation")
            models, error = h.query_ollama_models(base_url=config.ollama_base_url)
            if error or target not in [m["name"] for m in models]:
                raise ValueError("Model is not installed")
        result = h.start_background_process(
            command=["ollama", "pull" if operation == "pull" else "rm", target],
            cwd=h.ROOT,
            log_path=path / "model_ops.log",
            meta_path=h.model_job_meta_path(path),
            kind=f"model_{operation}",
            extra={"model": target},
            env_overrides={"OLLAMA_HOST": config.ollama_base_url},
        )
    elif operation == "run":
        mode = data.get("mode", "normal")
        if mode not in {"normal", "continuous", "diagnostic", "resume"}:
            raise ValueError("Invalid mode")
        drafting = data.get("drafting_mode", config.drafting_mode)
        preset = data.get("free_runner_preset", config.cloud_free.free_runner_preset)
        benchmark = data.get("benchmark_preset", "free_smoke")
        quota = int(data.get("max_provider_quota_failures", 2))
        if (
            drafting not in h.SUPPORTED_DRAFTING_MODES
            or preset not in h.FREE_RUNNER_PRESETS
            or benchmark not in h.BENCHMARK_PRESETS
            or not 0 <= quota <= 20
        ):
            raise ValueError("Invalid run configuration")
        if provider == "gemini":
            if not h.has_gemini_api_key_source(
                api_key_env=env, api_key_value=key, config_api_key=config.model.gemini.api_key
            ):
                raise ValueError("Gemini API key is missing")
            recommendation = cloud_pool(path, config, preset)["recommendation"]
            if preset != h.FREE_RUNNER_MANUAL and recommendation:
                model = recommendation.model_id
        if mode == "resume":
            resume = h.describe_resume_state(
                project_dir=path,
                checkpoint=h.read_json_file(path / "checkpoint.json"),
                run_active=False,
                selected_model=h.provider_model_label(provider, model),
            )
            if not resume["can_resume"]:
                raise ValueError(resume["message"])
        result = h.start_background_process(
            command=h.build_run_command(
                provider,
                mode,
                model,
                env,
                path.name,
                preset if provider == "gemini" else None,
                benchmark if mode == "continuous" else None,
                quota if mode == "continuous" else None,
                drafting,
                gemini_api_key_override_env=h.UI_GEMINI_API_KEY_ENV if key else None,
            ),
            cwd=h.ROOT,
            log_path=path / "run.log",
            meta_path=h.run_meta_path(path),
            kind="run",
            extra={
                "model": h.provider_model_label(provider, model),
                "mode": mode,
                "provider": provider,
                "drafting_mode": drafting,
            },
            env_overrides=h.build_provider_env_overrides(provider, env, key),
        )
    else:
        raise ValueError("Unknown action")
    if result.error:
        raise ValueError(result.error)
    return {"pid": result.pid}


def serialize(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Request bodies may contain credentials; never log them.

    def respond(self, payload, code=200, content_type="application/json; charset=utf-8"):
        body = (
            json.dumps(payload, default=serialize, ensure_ascii=False).encode()
            if isinstance(payload, (dict, list))
            else payload
        )
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' blob: data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def trusted(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (
            origin is None or origin in {f"http://{host}" for host in hosts}
        )

    def do_GET(self):
        if not self.trusted():
            self.respond({"error": "Untrusted origin"}, 403)
            return
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        try:
            if url.path == "/api/bootstrap":
                self.respond(
                    {
                        "token": TOKEN,
                        "projects": h.discover_project_names(h.PROJECTS_DIR),
                        "config": config_public(),
                        "translations": TRANSLATIONS,
                    }
                )
            elif url.path == "/api/workspace":
                self.respond(workspace(query.get("project", "")))
            elif url.path == "/api/status":
                self.respond(status(query.get("project", ""), query.get("model", "")))
            elif url.path == "/api/output":
                self.respond(output(query.get("project", ""), int(query.get("id", "-1"))))
            elif url.path == "/api/analytics":
                self.respond(analytics(query.get("project", "")))
            else:
                files = {
                    "/": "index.html",
                    "/app.js": "app.js",
                    "/styles.css": "styles.css",
                    "/architecture.js": "architecture.js",
                    "/favicon.svg": "favicon.svg",
                    "/vendor/marked.js": "vendor/marked.js",
                    "/vendor/purify.js": "vendor/purify.js",
                }
                if url.path not in files:
                    self.respond({"error": "Not found"}, 404)
                    return
                file = WEB / files[url.path]
                self.respond(
                    file.read_bytes(),
                    content_type=mimetypes.guess_type(file)[0] or "application/octet-stream",
                )
        except (ValueError, OSError, KeyError) as exc:
            self.respond({"error": str(exc)}, 400)

    def do_POST(self):
        if not self.trusted() or not secrets.compare_digest(
            self.headers.get("X-Dashboard-Token", ""), TOKEN
        ):
            self.respond({"error": "Untrusted request"}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2_000_000 or urlsplit(self.path).path != "/api/action":
                raise ValueError("Invalid request")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Invalid request")
            if not ACTION_LOCK.acquire(blocking=False):
                self.respond({"error": "Another operation is in progress"}, 409)
                return
            try:
                result = action(data)
            finally:
                ACTION_LOCK.release()
            self.respond(result)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.respond({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Auto research agent · http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

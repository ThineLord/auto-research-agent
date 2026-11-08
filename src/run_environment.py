"""Bounded, credential-free execution provenance (no model generation)."""

from __future__ import annotations

import hashlib
import platform
import re
from importlib import metadata
from pathlib import Path

from .config import query_ollama_api_models
from .llm import OllamaClient

RUNTIME_DISTRIBUTIONS = ("google-genai", "requests", "PyYAML", "rich", "streamlit")


def installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def collect_run_environment(llm: object = None) -> dict:
    """Report versions, never environment variables, endpoint URLs or error bodies."""
    constraints = Path(__file__).resolve().parents[1] / "requirements" / "constraints.txt"
    try:
        constraints_hash = hashlib.sha256(constraints.read_bytes()).hexdigest()
    except OSError:
        constraints_hash = None
    result = {
        "application_version": installed_version("auto-research-agent"),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "dependencies": {name: installed_version(name) for name in RUNTIME_DISTRIBUTIONS},
        "constraints_sha256": constraints_hash,
        "ollama_model_digest": None,
        "ollama_digest_status": "not_applicable",
    }
    if isinstance(llm, OllamaClient):
        result["ollama_digest_status"] = "unavailable"
        models, error = query_ollama_api_models(base_url=llm.base_url, timeout_seconds=2)
        if not error:
            target = llm.model if ":" in llm.model else f"{llm.model}:latest"
            for model in models:
                name = model["name"] if ":" in model["name"] else f"{model['name']}:latest"
                digest = model.get("id", "")
                if name == target and re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", digest):
                    result["ollama_model_digest"] = digest
                    result["ollama_digest_status"] = "available"
                    break
    return result

from __future__ import annotations

import hashlib
import hmac
import secrets

_PRIVATE_PATH_ID_KEY = secrets.token_bytes(32)
_PRIVATE_PATH_ID_DOMAIN = b"auto-research-agent:ollama-health:path:v1\0"


def private_ollama_path_id(normalized_path: str) -> str:
    """Return a process-local opaque identity for a private Ollama URL path."""
    encoded_path = str(normalized_path).encode("utf-8", errors="surrogatepass")
    return hmac.new(
        _PRIVATE_PATH_ID_KEY,
        _PRIVATE_PATH_ID_DOMAIN + encoded_path,
        hashlib.sha256,
    ).hexdigest()

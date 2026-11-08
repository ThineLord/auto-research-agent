"""Import smoke checks for CI and local development."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"


def discover_modules() -> list[str]:
    modules = ["src"]
    modules.extend(
        module.name
        for module in pkgutil.walk_packages([str(SRC_DIR)], prefix="src.")
        if not module.ispkg
    )
    modules.append("ui.app")
    return sorted(set(modules))


def main() -> int:
    sys.path.insert(0, str(ROOT))
    for module_name in discover_modules():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - import smoke checks should report any failure.
            print(f"FAILED importing {module_name}: {exc}", file=sys.stderr)
            return 1
        print(f"import ok: {module_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

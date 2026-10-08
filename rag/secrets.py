"""Read secrets from the environment, falling back to a local .env file.

.env is gitignored. Never put a key in a tracked file, a config default or a log line.
"""

import os
from pathlib import Path

from rag.config import ROOT


def load_env(path: Path = ROOT / ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding variables already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setting(name: str, default: str) -> str:
    """An environment or .env value with a fallback, for command-line defaults."""
    load_env()
    return os.environ.get(name) or default


def require(name: str) -> str:
    load_env()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Put it in the environment or in .env")
    return value

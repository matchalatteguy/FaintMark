"""Resolve the private data home without losing pre-rename watermark records."""

import os
from pathlib import Path


def resolve_home(home=None):
    configured = home or os.environ.get("FAINTMARK_HOME") or os.environ.get("COPYMARK_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    current = Path.home() / ".faintmark"
    legacy = Path.home() / ".copymark"
    if not (current / "registry.sqlite3").exists() and (legacy / "registry.sqlite3").exists():
        return legacy.resolve()
    return current.resolve()

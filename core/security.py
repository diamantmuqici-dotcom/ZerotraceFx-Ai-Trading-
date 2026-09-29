"""Security primitives used at API and local-storage boundaries."""
from __future__ import annotations

import hmac
from pathlib import Path


def valid_bearer(supplied: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(supplied.encode(), expected.encode())


def safe_child_path(root: str, relative: str) -> Path:
    base = Path(root).resolve(); candidate = (base / relative).resolve()
    if candidate != base and base not in candidate.parents: raise ValueError("path escapes root")
    return candidate

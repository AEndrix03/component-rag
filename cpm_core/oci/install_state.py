"""Local install lock helpers for OCI-installed packets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def install_lock_path(workspace_root: Path, packet_name: str) -> Path:
    return workspace_root / "state" / "install" / f"{packet_name}.lock.json"


def read_install_lock(workspace_root: Path, packet_name: str) -> dict[str, Any] | None:
    path = install_lock_path(workspace_root, packet_name)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def write_install_lock(workspace_root: Path, packet_name: str, payload: dict[str, Any]) -> Path:
    path = install_lock_path(workspace_root, packet_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

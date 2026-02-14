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
    return _normalize_install_lock(payload)


def write_install_lock(workspace_root: Path, packet_name: str, payload: dict[str, Any]) -> Path:
    path = install_lock_path(workspace_root, packet_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _normalize_install_lock(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if not isinstance(normalized.get("sources"), list):
        packet_ref = str(normalized.get("packet_ref") or "").strip()
        packet_digest = str(normalized.get("packet_digest") or "").strip()
        if packet_ref and packet_digest:
            normalized["sources"] = [
                {
                    "uri": f"oci://{packet_ref}",
                    "digest": packet_digest,
                    "signature": bool(normalized.get("signature", False)),
                    "sbom": bool(normalized.get("sbom", False)),
                    "provenance": bool(normalized.get("provenance", False)),
                    "trust_score": float(normalized.get("trust_score", 0.0)),
                }
            ]
    if "trust_score" not in normalized:
        normalized["trust_score"] = 0.0
    return normalized

"""Catalog helpers for OCI packet discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CPM_CATALOG_MEDIATYPE = "application/vnd.cpm.catalog.v1+jsonl"


def parse_catalog_jsonl(payload: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in payload.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def write_catalog_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    lines = [json.dumps(entry, sort_keys=True) for entry in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

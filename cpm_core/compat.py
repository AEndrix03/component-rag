"""Compatibility helpers for transitioning from legacy CPM layouts and commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from cpm_core.workspace import WorkspaceLayout


@dataclass(frozen=True)
class LegacyCommandAlias:
    """Alias metadata that maps old CPM commands to their new equivalents."""

    legacy: str
    replacement: str
    note: str | None = None


LEGACY_COMMAND_ALIASES: tuple[LegacyCommandAlias, ...] = (
    LegacyCommandAlias(
        legacy="embed",
        replacement="embedding helper under cpm_cli/cli.py",
        note="configures providers with cpm embed add/list/remove/set-default/test",
    ),
    LegacyCommandAlias(
        legacy="lookup",
        replacement="cpm pkg list",
        note="legacy discovery shortcut mapped to package listing",
    ),
    LegacyCommandAlias(
        legacy="use",
        replacement="cpm pkg use",
        note="pin and activate an installed package version",
    ),
    LegacyCommandAlias(
        legacy="prune",
        replacement="cpm pkg prune",
        note="remove old package versions while keeping active/pinned",
    ),
    LegacyCommandAlias(
        legacy="mcp serve",
        replacement="cpm serve",
        note="historical alias retained for compatibility",
    ),
)

LEGACY_COMMAND_TOKENS: frozenset[str] = frozenset(
    {
        "lookup",
        "use",
        "prune",
        "mcp",
        "pkg:list",
        "pkg:use",
        "pkg:prune",
        "pkg:remove",
        "embed:add",
        "embed:list",
        "embed:remove",
        "embed:set-default",
        "embed:test",
        "embed:status",
    }
)


@dataclass(frozen=True)
class LegacyLayoutIssue:
    """Represents a legacy package or artifact that should move into the new layout."""

    current_path: Path
    packet_name: str | None
    packet_version: str | None
    suggested_path: Path


def detect_legacy_layout(root: Path, layout: WorkspaceLayout) -> list[LegacyLayoutIssue]:
    """Return a list of legacy packet paths that should be migrated."""

    known_dirs = {
        layout.packages_dir.name,
        layout.cache_dir.name,
        layout.plugins_dir.name,
        layout.state_dir.name,
        layout.config_dir.name,
        layout.logs_dir.name,
    }
    issues: list[LegacyLayoutIssue] = []
    visited: set[str] = set()

    def _register(candidate: Path) -> None:
        resolved = str(candidate.resolve())
        if resolved in visited:
            return
        visited.add(resolved)
        if not _is_legacy_packet_root(candidate):
            return
        packet_name, packet_version = _extract_packet_metadata(candidate)
        suggested = layout.packages_dir / (packet_name or candidate.name)
        version_segment = packet_version or "legacy"
        suggested = suggested / version_segment
        issues.append(
            LegacyLayoutIssue(
                current_path=candidate,
                packet_name=packet_name,
                packet_version=packet_version,
                suggested_path=suggested,
            )
        )

    for child in root.iterdir():
        if not child.is_dir() or child.name in known_dirs:
            continue
        _register(child)
        for nested in child.iterdir():
            if not nested.is_dir():
                continue
            _register(nested)
    return issues


def _is_legacy_packet_root(path: Path) -> bool:
    if not path.exists():
        return False
    if (path / "manifest.json").is_file():
        return True
    if (path / "cpm.yml").is_file():
        return True
    if (path / "docs.jsonl").is_file():
        return True
    if (path / "faiss" / "index.faiss").is_file():
        return True
    return False


def _extract_packet_metadata(packet_root: Path) -> tuple[str | None, str | None]:
    manifest = _read_json(packet_root / "manifest.json")
    yaml_meta = _read_yaml(packet_root / "cpm.yml")
    name = None
    version = None
    if manifest:
        name = manifest.get("packet_id") or manifest.get("cpm", {}).get("name")
        version = manifest.get("cpm", {}).get("version")
    if yaml_meta:
        name = name or yaml_meta.get("name")
        version = version or yaml_meta.get("version")
    return name, version


def _read_json(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_yaml(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items() if k is not None}
    except Exception:
        return None
    return None

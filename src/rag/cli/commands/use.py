# rag/cli/commands/use.py
from __future__ import annotations

from pathlib import Path

from ..core.cpm_pkg import (
    parse_semver,
    version_dir,
    set_pinned_version,
)

def _parse_spec(spec: str) -> tuple[str, str]:
    if "@" not in spec:
        raise SystemExit("[cpm:use] expected name@x.y.z")
    name, version = spec.split("@", 1)
    name = name.strip()
    version = version.strip()
    parse_semver(version)
    return name, version


def cmd_cpm_use(args) -> None:
    cpm_dir = Path(args.cpm_dir or ".cpm").resolve()
    name, version = _parse_spec(args.spec)
    vd = version_dir(cpm_dir, name, version)
    if not vd.exists():
        raise SystemExit(f"[cpm:use] version not installed locally: {name}@{version}")
    set_pinned_version(cpm_dir, name, version)
    print(f"[cpm:use] current={name}@{version}")

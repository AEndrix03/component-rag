# rag/cli/commands/uninstall.py
from __future__ import annotations

import shutil
from pathlib import Path

from ..core.cpm_pkg import (
    parse_semver,
    installed_versions,
    max_semver,
    packet_root,
    version_dir,
    set_pinned_version,
)

def _parse_spec_optional(spec: str) -> tuple[str, str | None]:
    if "@" not in spec:
        return spec.strip(), None
    name, version = spec.split("@", 1)
    name = name.strip()
    version = version.strip()
    if not name:
        raise SystemExit("[cpm:uninstall] missing name")
    if version:
        parse_semver(version)
    return name, (version or None)


def cmd_cpm_uninstall(args) -> None:
    cpm_dir = Path(args.cpm_dir or ".cpm").resolve()
    name, version = _parse_spec_optional(args.spec)

    root = packet_root(cpm_dir, name)
    if not root.exists():
        raise SystemExit(f"[cpm:uninstall] not installed: {name}")

    if version is None:
        shutil.rmtree(root, ignore_errors=True)
        print(f"[cpm:uninstall] removed {name} (all versions)")
        return

    vd = version_dir(cpm_dir, name, version)
    if not vd.exists():
        raise SystemExit(f"[cpm:uninstall] version not installed: {name}@{version}")

    shutil.rmtree(vd, ignore_errors=True)

    remaining = installed_versions(cpm_dir, name)
    if not remaining:
        shutil.rmtree(root, ignore_errors=True)
        print(f"[cpm:uninstall] removed {name}@{version} (no versions left, removed packet)")
        return

    new_pin = max_semver(remaining)
    if new_pin:
        set_pinned_version(cpm_dir, name, new_pin)
    print(f"[cpm:uninstall] removed {name}@{version}; current={new_pin}")

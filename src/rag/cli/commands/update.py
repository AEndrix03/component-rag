# rag/cli/commands/update.py
from __future__ import annotations

import shutil
from pathlib import Path

from ..core.cpm_pkg import (
    RegistryClient,
    parse_semver,
    registry_latest_version,
    packet_root,
    download_and_extract,
    set_pinned_version,
)

def _parse_spec_optional(spec: str) -> tuple[str, str | None]:
    if "@" not in spec:
        return spec.strip(), None
    name, version = spec.split("@", 1)
    name = name.strip()
    version = version.strip()
    if not name:
        raise SystemExit("[cpm:update] missing name")
    if version:
        parse_semver(version)
    return name, (version or None)


def cmd_cpm_update(args) -> None:
    cpm_dir = Path(args.cpm_dir or ".cpm").resolve()
    registry = (args.registry or "").rstrip("/")
    if not registry:
        raise SystemExit("[cpm:update] missing --registry")

    name, requested = _parse_spec_optional(args.spec)
    root = packet_root(cpm_dir, name)
    if not root.exists():
        raise SystemExit(f"[cpm:update] {name} not installed. Run: rag cpm install {name}@x.y.z --registry {registry}")

    client = RegistryClient(registry)

    version = requested
    if version is None:
        version = registry_latest_version(client, name)
    else:
        # also verify remote exists
        if not client.exists(name, version):
            raise SystemExit(f"[cpm:update] not found on registry: {name}@{version}")

    if args.purge:
        shutil.rmtree(root, ignore_errors=True)

    # download/extract (overwrites files inside that version dir, other versions remain)
    vd = download_and_extract(client, name, version, cpm_dir)
    set_pinned_version(cpm_dir, name, version)

    print(f"[cpm:update] ok {name}@{version}")
    print(f"[cpm:update] dir={vd.as_posix()}")

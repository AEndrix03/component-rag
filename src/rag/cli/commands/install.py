# rag/cli/commands/install.py
from __future__ import annotations

from pathlib import Path

from ..core.cpm_pkg import (
    RegistryClient,
    parse_semver,
    download_and_extract,
    set_pinned_version,
)

def _parse_spec(spec: str) -> tuple[str, str]:
    if "@" not in spec:
        raise SystemExit("[cpm:install] expected name@x.y.z")
    name, version = spec.split("@", 1)
    name = name.strip()
    version = version.strip()
    if not name:
        raise SystemExit("[cpm:install] missing name")
    parse_semver(version)
    return name, version


def cmd_cpm_install(args) -> None:
    cpm_dir = Path(args.cpm_dir or ".cpm").resolve()
    registry = (args.registry or "").rstrip("/")
    if not registry:
        raise SystemExit("[cpm:install] missing --registry")

    name, version = _parse_spec(args.spec)

    client = RegistryClient(registry)
    if not client.exists(name, version):
        raise SystemExit(f"[cpm:install] not found on registry: {name}@{version}")

    vd = download_and_extract(client, name, version, cpm_dir)
    set_pinned_version(cpm_dir, name, version)

    print(f"[cpm:install] installed {name}@{version}")
    print(f"[cpm:install] dir={vd.as_posix()}")

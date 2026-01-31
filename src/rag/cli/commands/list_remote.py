# rag/cli/commands/list_remote.py
from __future__ import annotations

import json

from ..core.cpm_pkg import RegistryClient

def cmd_cpm_list_remote(args) -> None:
    registry = (args.registry or "").rstrip("/")
    if not registry:
        raise SystemExit("[cpm:list-remote] missing --registry")

    client = RegistryClient(registry)
    data = client.list(args.name, include_yanked=getattr(args, "include_yanked", False))

    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    versions = data.get("versions") or []
    if not versions:
        print("(no versions)")
        return

    for v in versions:
        print(
            f"{args.name}@{v['version']} sha256={v.get('sha256')} size={v.get('size_bytes')} "
            f"published_at={v.get('published_at')} yanked={v.get('yanked')}"
        )

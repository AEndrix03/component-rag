from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from .models import LocalPacket


def _safe_cache_key(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in raw)


def directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    root = root.resolve()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


class SourceCache:
    def __init__(self, workspace_root: Path, *, max_objects: int = 64) -> None:
        self.workspace_root = workspace_root.resolve()
        self.root = self.workspace_root / "cache"
        self.objects = self.root / "objects"
        self.max_objects = max(int(max_objects), 1)
        self.objects.mkdir(parents=True, exist_ok=True)

    def materialize_directory(self, source_dir: Path, *, digest: str) -> LocalPacket:
        key = _safe_cache_key(digest)
        target = self.objects / key
        if target.exists():
            os.utime(target, None)
            return LocalPacket(path=target, cache_key=key, cached=True)
        shutil.copytree(source_dir, target)
        self._evict_if_needed()
        return LocalPacket(path=target, cache_key=key, cached=False)

    def _evict_if_needed(self) -> None:
        objects = [item for item in self.objects.iterdir() if item.is_dir()]
        if len(objects) <= self.max_objects:
            return
        for stale in sorted(objects, key=lambda item: item.stat().st_mtime)[: len(objects) - self.max_objects]:
            shutil.rmtree(stale, ignore_errors=True)

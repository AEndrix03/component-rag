from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PacketReference:
    uri: str
    resolved_uri: str
    digest: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalPacket:
    path: Path
    cache_key: str
    cached: bool


@dataclass(frozen=True)
class UpdateInfo:
    has_update: bool
    latest_digest: str | None = None
    detail: str | None = None

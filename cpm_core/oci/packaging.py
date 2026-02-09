"""CPM packet packaging helpers for OCI artifacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from cpm_core.packet import load_manifest

CPM_OCI_MANIFEST = "packet.manifest.json"
CPM_OCI_LOCK = "packet.lock.json"
CPM_LAYER_MEDIATYPE = "application/vnd.cpm.packet.layer.v1.tar+gzip"
CPM_MANIFEST_MEDIATYPE = "application/vnd.cpm.packet.manifest.v1+json"
CPM_LOCK_MEDIATYPE = "application/vnd.cpm.packet.lock.v1+json"

_BASE_PACKET_FILES = (
    "cpm.yml",
    "manifest.json",
    "docs.jsonl",
)

_EMBED_PACKET_FILES = (
    "vectors.f16.bin",
    "faiss/index.faiss",
)


@dataclass(frozen=True)
class OciPacketLayout:
    packet_name: str
    packet_version: str
    staging_dir: Path
    files: tuple[Path, ...]
    media_types: dict[str, str]


def package_ref_for(name: str, version: str, repository: str) -> str:
    repo = repository.rstrip("/")
    return f"{repo}/{name}:{version}"


def digest_ref_for(repository: str, name: str, digest: str) -> str:
    repo = repository.rstrip("/")
    return f"{repo}/{name}@{digest}"


def build_oci_layout(packet_dir: Path, staging_dir: Path, *, include_embeddings: bool = True) -> OciPacketLayout:
    packet_dir = packet_dir.resolve()
    if not packet_dir.exists():
        raise FileNotFoundError(f"packet directory not found: {packet_dir}")

    raw_manifest = load_manifest(packet_dir / "manifest.json")
    packet_name = str(raw_manifest.cpm.get("name") or raw_manifest.packet_id or packet_dir.parent.name).strip()
    packet_version = str(raw_manifest.cpm.get("version") or packet_dir.name).strip()
    if not packet_name or not packet_version:
        raise ValueError("packet name/version are required to build OCI layout")

    staging_dir = staging_dir.resolve()
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    media_types: dict[str, str] = {}
    included: list[Path] = []

    payload_dir = staging_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    packet_files = list(_BASE_PACKET_FILES)
    if include_embeddings:
        packet_files.extend(_EMBED_PACKET_FILES)

    for rel in packet_files:
        src = packet_dir / rel
        if not src.exists():
            continue
        dst = payload_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        included.append(dst)

    manifest_payload = {
        "schema": "cpm-oci/v1",
        "packet": {"name": packet_name, "version": packet_version},
        "source_manifest": raw_manifest.to_dict(),
        "payload_root": "payload",
        "options": {"include_embeddings": include_embeddings},
    }
    oci_manifest_path = staging_dir / CPM_OCI_MANIFEST
    oci_manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    included.append(oci_manifest_path)
    media_types[oci_manifest_path.name] = CPM_MANIFEST_MEDIATYPE

    lock_path = packet_dir / "packet.lock.json"
    if lock_path.exists():
        oci_lock_path = staging_dir / CPM_OCI_LOCK
        shutil.copy2(lock_path, oci_lock_path)
        included.append(oci_lock_path)
        media_types[oci_lock_path.name] = CPM_LOCK_MEDIATYPE

    return OciPacketLayout(
        packet_name=packet_name,
        packet_version=packet_version,
        staging_dir=staging_dir,
        files=tuple(included),
        media_types=media_types,
    )

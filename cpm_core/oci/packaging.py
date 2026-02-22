"""CPM packet packaging helpers for OCI artifacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from cpm_core.packet import load_manifest
from cpm_core.oci.packet_metadata import build_packet_metadata, file_sha256_hex

CPM_OCI_MANIFEST = "packet.manifest.json"
CPM_OCI_LOCK = "packet.lock.json"
CPM_LAYER_MEDIATYPE = "application/vnd.cpm.packet.layer.v1.tar+gzip"
CPM_MANIFEST_MEDIATYPE = "application/vnd.cpm.packet.manifest.v1+json"
CPM_LOCK_MEDIATYPE = "application/vnd.cpm.packet.lock.v1+json"

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


def build_oci_layout(
    packet_dir: Path,
    staging_dir: Path,
    *,
    include_embeddings: bool = True,
    include_docs: bool = True,
    minimal: bool = False,
    include_source_manifest: bool = False,
) -> OciPacketLayout:
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

    if minimal:
        include_docs = False
        include_embeddings = False

    payload_dir = staging_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    packet_files = ["cpm.yml", "manifest.json"]
    if include_docs:
        packet_files.append("docs.jsonl")
    if include_embeddings:
        packet_files.extend(_EMBED_PACKET_FILES)

    payload_entries: list[dict[str, object]] = []
    payload_included: list[Path] = []
    for rel in packet_files:
        src = packet_dir / rel
        if not src.exists():
            continue
        dst = payload_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        payload_included.append(dst)
        payload_entries.append(
            {
                "name": rel,
                "digest": f"sha256:{file_sha256_hex(dst)}",
                "size": int(dst.stat().st_size),
            }
        )

    source_manifest = raw_manifest.to_dict()
    manifest_payload = build_packet_metadata(
        packet_name=packet_name,
        packet_version=packet_version,
        source_manifest=source_manifest,
        payload_files=payload_entries,
        payload_full_ref=None,
        source_manifest_digest=f"sha256:{file_sha256_hex(packet_dir / 'manifest.json')}",
        include_source_manifest=include_source_manifest,
        build_options={
            "minimal": minimal,
            "include_docs": include_docs,
            "include_embeddings": include_embeddings,
        },
    )
    manifest_payload["payload_root"] = "payload"
    oci_manifest_path = staging_dir / CPM_OCI_MANIFEST
    oci_manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    included.append(oci_manifest_path)
    included.extend(payload_included)
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

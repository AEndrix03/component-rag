"""Schema helpers for packet.manifest.json metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

PACKET_METADATA_SCHEMA = "cpm.packet.metadata"
PACKET_METADATA_SCHEMA_VERSION = "1.0"


def file_sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_packet_metadata(
    *,
    packet_name: str,
    packet_version: str,
    source_manifest: dict[str, Any],
    payload_files: list[dict[str, object]],
    payload_full_ref: str | None,
    source_manifest_digest: str | None,
    include_source_manifest: bool = False,
    build_options: dict[str, object] | None = None,
) -> dict[str, Any]:
    cpm = source_manifest.get("cpm") if isinstance(source_manifest.get("cpm"), dict) else {}
    packet_payload: dict[str, Any] = {
        "name": packet_name,
        "version": packet_version,
    }
    for optional_key in ("description", "tags", "kind", "entrypoints", "capabilities"):
        value = cpm.get(optional_key)
        if value is not None:
            packet_payload[optional_key] = value

    compat_payload: dict[str, Any] = {}
    compat_source = cpm.get("compat") if isinstance(cpm.get("compat"), dict) else {}
    for compat_key in ("os", "arch", "cpm_min_version"):
        value = compat_source.get(compat_key)
        if value is not None:
            compat_payload[compat_key] = value

    payload_payload: dict[str, Any] = {"files": payload_files}
    if payload_full_ref:
        payload_payload["full_ref"] = payload_full_ref

    source_payload: dict[str, Any] = {}
    if source_manifest_digest:
        source_payload["manifest_digest"] = source_manifest_digest
    if build_options:
        source_payload["build"] = build_options

    metadata: dict[str, Any] = {
        "schema": PACKET_METADATA_SCHEMA,
        "schema_version": PACKET_METADATA_SCHEMA_VERSION,
        "packet": packet_payload,
        "payload": payload_payload,
    }
    if compat_payload:
        metadata["compat"] = compat_payload
    if source_payload:
        metadata["source"] = source_payload
    if include_source_manifest:
        metadata["source_manifest"] = source_manifest
    return metadata


def validate_packet_metadata(payload: dict[str, Any]) -> None:
    if payload.get("schema") != PACKET_METADATA_SCHEMA:
        raise ValueError("invalid metadata schema")
    if str(payload.get("schema_version") or "") != PACKET_METADATA_SCHEMA_VERSION:
        raise ValueError("unsupported metadata schema_version")
    packet = payload.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("metadata.packet must be an object")
    if not str(packet.get("name") or "").strip():
        raise ValueError("metadata.packet.name is required")
    if not str(packet.get("version") or "").strip():
        raise ValueError("metadata.packet.version is required")
    payload_node = payload.get("payload")
    if not isinstance(payload_node, dict):
        raise ValueError("metadata.payload must be an object")
    files = payload_node.get("files")
    if not isinstance(files, list):
        raise ValueError("metadata.payload.files must be a list")
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("metadata.payload.files entries must be objects")
        if not str(item.get("name") or "").strip():
            raise ValueError("metadata.payload.files[].name is required")

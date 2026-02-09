from __future__ import annotations

import json
from pathlib import Path

from cpm_core.oci import (
    CPM_OCI_LOCK,
    CPM_OCI_MANIFEST,
    build_oci_layout,
    digest_ref_for,
    package_ref_for,
)


def _write_packet_fixture(root: Path) -> Path:
    packet = root / "demo" / "1.0.0"
    (packet / "faiss").mkdir(parents=True, exist_ok=True)
    (packet / "cpm.yml").write_text("name: demo\nversion: 1.0.0\n", encoding="utf-8")
    (packet / "docs.jsonl").write_text("{\"id\": \"1\", \"text\": \"hello\"}\n", encoding="utf-8")
    (packet / "vectors.f16.bin").write_bytes(b"\x00\x01")
    (packet / "faiss" / "index.faiss").write_bytes(b"INDEX")
    manifest = {
        "schema_version": "1.0",
        "packet_id": "demo",
        "embedding": {"provider": "x", "model": "m", "dim": 2, "dtype": "float16", "normalized": True},
        "cpm": {"name": "demo", "version": "1.0.0"},
    }
    (packet / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (packet / "packet.lock.json").write_text("{\"lockfileVersion\":1}", encoding="utf-8")
    return packet


def test_build_oci_layout_collects_expected_files(tmp_path: Path) -> None:
    packet = _write_packet_fixture(tmp_path)
    layout = build_oci_layout(packet, tmp_path / "staging")

    names = {path.name for path in layout.files}
    assert CPM_OCI_MANIFEST in names
    assert CPM_OCI_LOCK in names
    assert layout.packet_name == "demo"
    assert layout.packet_version == "1.0.0"
    assert (layout.staging_dir / "payload" / "docs.jsonl").exists()
    assert (layout.staging_dir / CPM_OCI_MANIFEST).exists()


def test_build_oci_layout_can_exclude_embeddings(tmp_path: Path) -> None:
    packet = _write_packet_fixture(tmp_path)
    layout = build_oci_layout(packet, tmp_path / "staging", include_embeddings=False)

    assert (layout.staging_dir / "payload" / "docs.jsonl").exists()
    assert not (layout.staging_dir / "payload" / "vectors.f16.bin").exists()
    assert not (layout.staging_dir / "payload" / "faiss" / "index.faiss").exists()


def test_ref_mapping_helpers() -> None:
    assert package_ref_for("demo", "1.0.0", "registry.local/project") == "registry.local/project/demo:1.0.0"
    assert (
        digest_ref_for("registry.local/project", "demo", "sha256:abc")
        == "registry.local/project/demo@sha256:abc"
    )

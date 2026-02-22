from __future__ import annotations

import json
from pathlib import Path

from cpm_cli.main import main as cli_main


def _create_local_package(workspace_root: Path) -> None:
    packet = workspace_root / "packages" / "demo" / "1.0.0"
    packet.mkdir(parents=True, exist_ok=True)
    (packet / "manifest.json").write_text(
        json.dumps({"cpm": {"name": "demo", "version": "1.0.0", "kind": "retriever", "capabilities": ["rag"]}}),
        encoding="utf-8",
    )


def test_catalog_build_writes_jsonl(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _create_local_package(workspace_root)

    code = cli_main(["catalog", "--format", "json"], start_dir=tmp_path)
    assert code == 0
    output = workspace_root / "cache" / "catalog" / "cpm-catalog.jsonl"
    assert output.exists()
    lines = [line for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["name"] == "demo"
    assert entry["version"] == "1.0.0"


def test_catalog_publish_uses_catalog_mediatype(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _create_local_package(workspace_root)
    captured: dict[str, object] = {}

    class _FakeOciClient:
        def __init__(self, config):
            captured["config"] = config

        def push(self, ref, spec):
            captured["ref"] = ref
            captured["media_types"] = dict(spec.media_types)
            return type("PushResult", (), {"ref": ref, "digest": "sha256:" + ("c" * 64)})()

    import cpm_core.builtins.catalog as catalog_mod

    monkeypatch.setattr(catalog_mod, "OciClient", _FakeOciClient)
    code = cli_main(
        ["catalog", "--publish-ref", "registry.local/project/cpm/catalog:latest", "--format", "json"],
        start_dir=tmp_path,
    )
    assert code == 0
    assert "cpm-catalog.jsonl" in captured["media_types"]

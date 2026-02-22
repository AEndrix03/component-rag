from __future__ import annotations

import json
from pathlib import Path

from cpm_cli.main import main as cli_main
from cpm_core.sources.models import PacketReference


def test_lookup_remote_returns_digest_pinned_uri(monkeypatch, tmp_path: Path, capfd) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))

    class _FakeResolver:
        def __init__(self, workspace_root: Path):
            self.workspace_root = workspace_root

        def lookup_metadata(self, uri: str):
            reference = PacketReference(
                uri=uri,
                resolved_uri="oci://registry.local/project/demo:latest",
                digest="sha256:" + ("a" * 64),
                metadata={"ref": "registry.local/project/demo:latest", "metadata_digest": "sha256:" + ("b" * 64)},
            )
            payload = {
                "packet": {"name": "demo", "version": "1.0.0", "entrypoints": ["run"], "capabilities": ["rag"]},
                "compat": {"os": ["linux"], "arch": ["amd64"]},
            }
            return reference, payload

    import cpm_core.builtins.lookup as lookup_mod

    monkeypatch.setattr(lookup_mod, "SourceResolver", _FakeResolver)
    code = cli_main(
        [
            "lookup",
            "--source-uri",
            "oci://registry.local/project/demo:latest",
            "--entrypoint",
            "run",
            "--format",
            "json",
        ],
        start_dir=tmp_path,
    )
    out = capfd.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["pinned_uri"].endswith("@sha256:" + ("a" * 64))
    assert payload["selected_entrypoint"] == "run"


def test_lookup_remote_applies_capability_filter(monkeypatch, tmp_path: Path, capfd) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))

    class _FakeResolver:
        def __init__(self, workspace_root: Path):
            self.workspace_root = workspace_root

        def lookup_metadata(self, uri: str):
            reference = PacketReference(
                uri=uri,
                resolved_uri="oci://registry.local/project/demo:latest",
                digest="sha256:" + ("a" * 64),
                metadata={"ref": "registry.local/project/demo:latest", "metadata_digest": "sha256:" + ("b" * 64)},
            )
            payload = {"packet": {"name": "demo", "version": "1.0.0", "capabilities": ["search"]}}
            return reference, payload

    import cpm_core.builtins.lookup as lookup_mod

    monkeypatch.setattr(lookup_mod, "SourceResolver", _FakeResolver)
    code = cli_main(
        [
            "lookup",
            "--source-uri",
            "oci://registry.local/project/demo:latest",
            "--capability",
            "rag",
        ],
        start_dir=tmp_path,
    )
    out = capfd.readouterr().out
    assert code == 1
    assert "missing capability=rag" in out


def test_lookup_can_resolve_source_from_catalog_file(monkeypatch, tmp_path: Path, capfd) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    catalog_dir = workspace_root / "cache" / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / "cpm-catalog.jsonl").write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "1.0.0",
                "tag": "1.0.0",
                "source_uri": "oci://registry.local/project/demo:1.0.0",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    class _FakeResolver:
        def __init__(self, workspace_root: Path):
            self.workspace_root = workspace_root

        def lookup_metadata(self, uri: str):
            assert uri == "oci://registry.local/project/demo:1.0.0"
            reference = PacketReference(
                uri=uri,
                resolved_uri="oci://registry.local/project/demo:1.0.0",
                digest="sha256:" + ("a" * 64),
                metadata={"ref": "registry.local/project/demo:1.0.0", "metadata_digest": "sha256:" + ("b" * 64)},
            )
            payload = {"packet": {"name": "demo", "version": "1.0.0"}}
            return reference, payload

    import cpm_core.builtins.lookup as lookup_mod

    monkeypatch.setattr(lookup_mod, "SourceResolver", _FakeResolver)
    code = cli_main(
        [
            "lookup",
            "--registry",
            "registry.local/project",
            "--name",
            "demo",
            "--version",
            "1.0.0",
            "--use-catalog",
        ],
        start_dir=tmp_path,
    )
    out = capfd.readouterr().out
    assert code == 0
    assert "pinned=oci://registry.local/project/demo@sha256:" in out

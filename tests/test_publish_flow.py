from __future__ import annotations

import json
from pathlib import Path

from cpm_cli.main import main as cli_main
from cpm_core.oci import OciCommandError


def _create_packet_dir(root: Path) -> Path:
    packet = root / "demo" / "1.0.0"
    (packet / "faiss").mkdir(parents=True, exist_ok=True)
    (packet / "cpm.yml").write_text("name: demo\nversion: 1.0.0\n", encoding="utf-8")
    (packet / "docs.jsonl").write_text("{\"id\":\"1\",\"text\":\"hello\"}\n", encoding="utf-8")
    (packet / "vectors.f16.bin").write_bytes(b"\x00\x01")
    (packet / "faiss" / "index.faiss").write_bytes(b"INDEX")
    (packet / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "packet_id": "demo",
                "embedding": {"provider": "x", "model": "m", "dim": 2, "dtype": "float16", "normalized": True},
                "cpm": {"name": "demo", "version": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    return packet


def test_publish_uses_oci_layout_and_reports_digest(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    packet_dir = _create_packet_dir(tmp_path)
    captured: dict[str, object] = {}

    class _FakeOciClient:
        def __init__(self, config):
            captured["config"] = config

        def push(self, ref, spec):
            captured["ref"] = ref
            captured["files"] = [str(path) for path in spec.files]
            return type("PushResult", (), {"ref": ref, "digest": "sha256:" + ("d" * 64)})()

    import cpm_core.builtins.publish as publish_mod

    monkeypatch.setattr(publish_mod, "OciClient", _FakeOciClient)
    code = cli_main(
        ["publish", "--from-dir", str(packet_dir), "--registry", "registry.local/project"],
        start_dir=tmp_path,
    )
    assert code == 0
    assert str(captured["ref"]).endswith("/demo:1.0.0")
    assert any("packet.manifest.json" in item for item in captured["files"])


def test_publish_no_embed_excludes_vectors(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    packet_dir = _create_packet_dir(tmp_path)
    captured: dict[str, object] = {}

    class _FakeOciClient:
        def __init__(self, config):
            captured["config"] = config

        def push(self, ref, spec):
            captured["files"] = [str(path) for path in spec.files]
            return type("PushResult", (), {"ref": ref, "digest": "sha256:" + ("d" * 64)})()

    import cpm_core.builtins.publish as publish_mod

    monkeypatch.setattr(publish_mod, "OciClient", _FakeOciClient)
    code = cli_main(
        ["publish", "--from-dir", str(packet_dir), "--registry", "registry.local/project", "--no-embed"],
        start_dir=tmp_path,
    )
    assert code == 0
    files = [str(item) for item in captured["files"]]
    assert not any("vectors.f16.bin" in item for item in files)
    assert not any("index.faiss" in item for item in files)


def test_publish_resolves_dist_fallback_and_normalizes_http_registry(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _create_packet_dir(tmp_path / "dist")
    captured: dict[str, object] = {}

    class _FakeOciClient:
        def __init__(self, config):
            captured["config"] = config

        def push(self, ref, spec):
            captured["ref"] = ref
            captured["files"] = [str(path) for path in spec.files]
            return type("PushResult", (), {"ref": ref, "digest": "sha256:" + ("d" * 64)})()

    import cpm_core.builtins.publish as publish_mod

    monkeypatch.setattr(publish_mod, "OciClient", _FakeOciClient)
    code = cli_main(
        ["publish", "--from-dir", "./demo", "--registry", "http://localhost:5000"],
        start_dir=tmp_path,
    )
    assert code == 0
    assert str(captured["ref"]) == "localhost:5000/demo:1.0.0"


def test_publish_resolves_existing_container_dir(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _create_packet_dir(tmp_path / "dist")
    captured: dict[str, object] = {}

    class _FakeOciClient:
        def __init__(self, config):
            captured["config"] = config

        def push(self, ref, spec):
            captured["ref"] = ref
            captured["files"] = [str(path) for path in spec.files]
            return type("PushResult", (), {"ref": ref, "digest": "sha256:" + ("d" * 64)})()

    import cpm_core.builtins.publish as publish_mod

    monkeypatch.setattr(publish_mod, "OciClient", _FakeOciClient)
    code = cli_main(
        ["publish", "--from-dir", str(tmp_path / "dist" / "demo"), "--registry", "localhost:5000"],
        start_dir=tmp_path,
    )
    assert code == 0
    assert str(captured["ref"]) == "localhost:5000/demo:1.0.0"


def test_publish_handles_oci_errors_without_traceback(monkeypatch, tmp_path: Path, capfd) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    packet_dir = _create_packet_dir(tmp_path)

    class _FakeOciClient:
        def __init__(self, config):
            _ = config

        def push(self, ref, spec):
            _ = (ref, spec)
            raise OciCommandError("oras CLI not found")

    import cpm_core.builtins.publish as publish_mod

    monkeypatch.setattr(publish_mod, "OciClient", _FakeOciClient)
    code = cli_main(
        ["publish", "--from-dir", str(packet_dir), "--registry", "registry.local/project"],
        start_dir=tmp_path,
    )
    captured = capfd.readouterr()
    assert code == 1
    assert "[cpm:publish] failed: oras CLI not found" in captured.out


def test_publish_reports_missing_manifest_for_invalid_from_dir(monkeypatch, tmp_path: Path, capfd) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    invalid_dir = tmp_path / "not-a-packet"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    code = cli_main(
        ["publish", "--from-dir", str(invalid_dir), "--registry", "localhost:5000"],
        start_dir=tmp_path,
    )
    captured = capfd.readouterr()
    assert code == 1
    assert "[cpm:publish] no packet found in --from-dir" in captured.out

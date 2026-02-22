from __future__ import annotations

import json
import shutil
from pathlib import Path

from cpm_cli.main import main as cli_main
from cpm_builtin.embeddings import EmbeddingProviderConfig, EmbeddingsConfigService


def _write_workspace_config(workspace_root: Path) -> None:
    config_dir = workspace_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        """[oci]
repository = "registry.local/project"
allowlist_domains = ["registry.local"]
strict_verify = false
require_signature = false
require_sbom = false
require_provenance = false
""",
        encoding="utf-8",
    )


def _write_embeddings_config(workspace_root: Path, *, with_artifacts: bool) -> None:
    service = EmbeddingsConfigService(workspace_root)
    model_artifacts = (
        {
            "source": "oci",
            "ref_template": "registry.local/models/{model}:latest",
        }
        if with_artifacts
        else None
    )
    service.add_provider(
        EmbeddingProviderConfig(
            name="provider-a",
            type="http",
            url="http://127.0.0.1:8000",
            model="model-a",
            http_base_url="http://127.0.0.1:8000",
            http_embeddings_path="/v1/embeddings",
            http_models_path="/v1/models",
            model_artifacts=model_artifacts,
        ),
        set_default=True,
    )


def _create_oci_packet_artifact(root: Path, *, model: str = "model-a") -> Path:
    artifact = root / "packet"
    payload_dir = artifact / "payload"
    (payload_dir / "faiss").mkdir(parents=True, exist_ok=True)
    (payload_dir / "cpm.yml").write_text("name: demo\nversion: 1.0.0\n", encoding="utf-8")
    (payload_dir / "docs.jsonl").write_text("{\"id\":\"1\",\"text\":\"hello\"}\n", encoding="utf-8")
    (payload_dir / "vectors.f16.bin").write_bytes(b"\x00\x01")
    (payload_dir / "faiss" / "index.faiss").write_bytes(b"INDEX")
    (payload_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "packet_id": "demo",
                "embedding": {"provider": "x", "model": model, "dim": 2, "dtype": "float16", "normalized": True},
                "cpm": {"name": "demo", "version": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (artifact / "packet.manifest.json").write_text(
        json.dumps(
            {
                "schema": "cpm-oci/v1",
                "packet": {"name": "demo", "version": "1.0.0"},
                "payload_root": "payload",
                "source_manifest": {
                    "supported_models": ["model-*"],
                    "recommended_model": model,
                    "suggested_retriever": "cpm:native-retriever",
                },
            }
        ),
        encoding="utf-8",
    )
    return artifact


def test_install_remote_only_provider(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _write_workspace_config(workspace_root)
    _write_embeddings_config(workspace_root, with_artifacts=False)
    packet_artifact = _create_oci_packet_artifact(tmp_path, model="model-a")

    class _FakeOciClient:
        def __init__(self, config):
            self.config = config

        def resolve(self, ref: str) -> str:
            return "sha256:" + ("a" * 64)

        def discover_referrers(self, subject_ref: str):
            del subject_ref
            return []

        def pull(self, ref: str, output_dir: Path):
            shutil.copytree(packet_artifact, output_dir, dirs_exist_ok=True)
            files = tuple(path for path in output_dir.rglob("*") if path.is_file())
            return type("PullResult", (), {"ref": ref, "digest": None, "files": files})()

    import cpm_core.builtins.install as install_mod

    monkeypatch.setattr(install_mod, "OciClient", _FakeOciClient)
    monkeypatch.setattr(
        install_mod,
        "_select_model",
        lambda **kwargs: {"model": "model-a", "provider": None, "suggested_retriever": "cpm:native-retriever"},
    )
    code = cli_main(["install", "demo@1.0.0", "--registry", "registry.local/project"], start_dir=tmp_path)
    assert code == 0
    assert (workspace_root / "packages" / "demo" / "1.0.0" / "cpm.yml").exists()
    lock = json.loads((workspace_root / "state" / "install" / "demo.lock.json").read_text(encoding="utf-8"))
    assert lock["selected_model"] == "model-a"
    assert "model_artifact" not in lock


def test_install_provider_with_model_artifact(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _write_workspace_config(workspace_root)
    _write_embeddings_config(workspace_root, with_artifacts=True)
    packet_artifact = _create_oci_packet_artifact(tmp_path, model="model-a")

    class _FakeOciClient:
        def __init__(self, config):
            self.config = config

        def resolve(self, ref: str) -> str:
            if "models/" in ref:
                return "sha256:" + ("b" * 64)
            return "sha256:" + ("a" * 64)

        def discover_referrers(self, subject_ref: str):
            del subject_ref
            return []

        def pull(self, ref: str, output_dir: Path):
            if "models/" in ref:
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "model.bin").write_bytes(b"MODEL")
            else:
                shutil.copytree(packet_artifact, output_dir, dirs_exist_ok=True)
            files = tuple(path for path in output_dir.rglob("*") if path.is_file())
            return type("PullResult", (), {"ref": ref, "digest": None, "files": files})()

    import cpm_core.builtins.install as install_mod

    monkeypatch.setattr(install_mod, "OciClient", _FakeOciClient)
    monkeypatch.setattr(
        install_mod,
        "_select_model",
        lambda **kwargs: {"model": "model-a", "provider": "provider-a", "suggested_retriever": "cpm:native-retriever"},
    )
    def _fake_model_artifact(**kwargs):
        del kwargs
        target = workspace_root / "cache" / "models" / "provider-a" / "model-a"
        target.mkdir(parents=True, exist_ok=True)
        (target / "model.bin").write_bytes(b"MODEL")
        return {
            "ref": "registry.local/models/model-a:latest",
            "digest": "sha256:" + ("b" * 64),
            "path": str(target),
        }

    monkeypatch.setattr(install_mod, "_maybe_pull_model_artifact", _fake_model_artifact)
    code = cli_main(["install", "demo@1.0.0", "--registry", "registry.local/project"], start_dir=tmp_path)
    assert code == 0
    lock = json.loads((workspace_root / "state" / "install" / "demo.lock.json").read_text(encoding="utf-8"))
    assert lock["model_artifact"]["digest"] == "sha256:" + ("b" * 64)
    assert Path(lock["model_artifact"]["path"]).exists()


def test_install_no_embed_skips_model_resolution(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _write_workspace_config(workspace_root)
    _write_embeddings_config(workspace_root, with_artifacts=False)
    packet_artifact = _create_oci_packet_artifact(tmp_path, model="model-a")

    class _FakeOciClient:
        def __init__(self, config):
            self.config = config

        def resolve(self, ref: str) -> str:
            return "sha256:" + ("a" * 64)

        def discover_referrers(self, subject_ref: str):
            del subject_ref
            return []

        def pull(self, ref: str, output_dir: Path):
            shutil.copytree(packet_artifact, output_dir, dirs_exist_ok=True)
            files = tuple(path for path in output_dir.rglob("*") if path.is_file())
            return type("PullResult", (), {"ref": ref, "digest": None, "files": files})()

    import cpm_core.builtins.install as install_mod

    monkeypatch.setattr(install_mod, "OciClient", _FakeOciClient)
    monkeypatch.setattr(install_mod, "_select_model", lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected")))
    code = cli_main(
        ["install", "demo@1.0.0", "--registry", "registry.local/project", "--no-embed"],
        start_dir=tmp_path,
    )
    assert code == 0
    target_dir = workspace_root / "packages" / "demo" / "1.0.0"
    assert not (target_dir / "vectors.f16.bin").exists()
    assert not (target_dir / "faiss" / "index.faiss").exists()
    lock = json.loads((workspace_root / "state" / "install" / "demo.lock.json").read_text(encoding="utf-8"))
    assert lock["no_embed"] is True
    assert lock["selected_model"] is None


def test_install_rejects_http_registry(tmp_path: Path, capfd) -> None:
    code = cli_main(
        ["install", "demo@1.0.0", "--registry", "http://localhost:5000"],
        start_dir=tmp_path,
    )
    out = capfd.readouterr().out
    assert code == 1
    assert "HTTP(S) registry URLs are not supported" in out


def test_install_falls_back_to_payload_manifest_when_source_manifest_missing(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    monkeypatch.setenv("RAG_CPM_DIR", str(workspace_root))
    _write_workspace_config(workspace_root)
    _write_embeddings_config(workspace_root, with_artifacts=False)
    packet_artifact = _create_oci_packet_artifact(tmp_path, model="model-a")
    metadata_path = packet_artifact / "packet.manifest.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("source_manifest", None)
    metadata["schema"] = "cpm.packet.metadata"
    metadata["schema_version"] = "1.0"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    class _FakeOciClient:
        def __init__(self, config):
            self.config = config

        def resolve(self, ref: str) -> str:
            return "sha256:" + ("a" * 64)

        def discover_referrers(self, subject_ref: str):
            del subject_ref
            return []

        def pull(self, ref: str, output_dir: Path):
            shutil.copytree(packet_artifact, output_dir, dirs_exist_ok=True)
            files = tuple(path for path in output_dir.rglob("*") if path.is_file())
            return type("PullResult", (), {"ref": ref, "digest": None, "files": files})()

    import cpm_core.builtins.install as install_mod

    monkeypatch.setattr(install_mod, "OciClient", _FakeOciClient)
    monkeypatch.setattr(
        install_mod,
        "_select_model",
        lambda **kwargs: {"model": "model-a", "provider": None, "suggested_retriever": "cpm:native-retriever"},
    )
    code = cli_main(["install", "demo@1.0.0", "--registry", "registry.local/project"], start_dir=tmp_path)
    assert code == 0

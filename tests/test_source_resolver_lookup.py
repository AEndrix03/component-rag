from __future__ import annotations

import json
from pathlib import Path

from cpm_core.oci import CPM_MANIFEST_MEDIATYPE
from cpm_core.sources.cache import SourceCache
from cpm_core.sources.resolver import OciSource


def _write_workspace_config(workspace_root: Path) -> None:
    config_dir = workspace_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        """[oci]
allowlist_domains = ["registry.local"]
strict_verify = false
require_signature = false
require_sbom = false
require_provenance = false
""",
        encoding="utf-8",
    )


def test_inspect_metadata_fetches_manifest_and_uses_cache(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    _write_workspace_config(workspace_root)
    calls = {"manifest": 0, "blob": 0}
    metadata_digest = "sha256:" + ("b" * 64)
    metadata_payload = {
        "schema": "cpm.packet.metadata",
        "schema_version": "1.0",
        "packet": {"name": "demo", "version": "1.0.0", "entrypoints": ["run"]},
        "payload": {"files": [{"name": "manifest.json"}]},
    }

    class _FakeOciClient:
        def __init__(self, config):
            self.config = config

        def resolve(self, ref: str) -> str:
            return "sha256:" + ("a" * 64)

        def fetch_manifest(self, ref: str):
            calls["manifest"] += 1
            return {"schemaVersion": 2, "layers": [{"mediaType": CPM_MANIFEST_MEDIATYPE, "digest": metadata_digest}]}

        def fetch_blob(self, ref: str, digest: str) -> bytes:
            calls["blob"] += 1
            assert digest == metadata_digest
            return json.dumps(metadata_payload).encode("utf-8")

        def discover_referrers(self, subject_ref: str):
            del subject_ref
            return []

    import cpm_core.sources.resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "OciClient", _FakeOciClient)
    source = OciSource(workspace_root)
    cache = SourceCache(workspace_root)

    ref1, payload1 = source.inspect_metadata("oci://registry.local/team/demo:1.0.0", cache)
    ref2, payload2 = source.inspect_metadata("oci://registry.local/team/demo:1.0.0", cache)

    assert ref1.digest == ref2.digest
    assert ref1.metadata["metadata_digest"] == metadata_digest
    assert payload1["packet"]["name"] == "demo"
    assert payload2["packet"]["name"] == "demo"
    assert calls["manifest"] == 1
    assert calls["blob"] == 1


def test_to_ref_appends_latest_tag() -> None:
    assert OciSource._to_ref("oci://registry.local/team/demo") == "registry.local/team/demo:latest"


def test_inspect_metadata_supports_legacy_metadata_schema(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    _write_workspace_config(workspace_root)
    metadata_digest = "sha256:" + ("b" * 64)

    class _FakeOciClient:
        def __init__(self, config):
            self.config = config

        def resolve(self, ref: str) -> str:
            return "sha256:" + ("a" * 64)

        def fetch_manifest(self, ref: str):
            return {"schemaVersion": 2, "layers": [{"mediaType": CPM_MANIFEST_MEDIATYPE, "digest": metadata_digest}]}

        def fetch_blob(self, ref: str, digest: str) -> bytes:
            return json.dumps(
                {
                    "schema": "cpm-oci/v1",
                    "packet": {"name": "demo", "version": "1.0.0"},
                    "payload_root": "payload",
                }
            ).encode("utf-8")

        def discover_referrers(self, subject_ref: str):
            del subject_ref
            return []

    import cpm_core.sources.resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "OciClient", _FakeOciClient)
    source = OciSource(workspace_root)
    cache = SourceCache(workspace_root)

    _, payload = source.inspect_metadata("oci://registry.local/team/demo:1.0.0", cache)
    assert payload["schema"] == "cpm.packet.metadata"
    assert payload["packet"]["name"] == "demo"

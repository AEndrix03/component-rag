from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

HTTP_OK = 200


class _FakeStorage:
    def __init__(self, **kwargs):
        del kwargs

    def ensure_bucket(self) -> None:
        return

    def head(self, key: str):
        del key

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        del key, data, content_type

    def get_streaming_body(self, key: str):
        del key
        return b""


def _load_registry_api_module() -> types.ModuleType:
    root = Path(__file__).resolve().parents[1]
    registry_src = root / "registry" / "src"
    sys.path.insert(0, str(registry_src))
    fake_botocore = types.ModuleType("botocore")
    fake_botocore_exceptions = types.ModuleType("botocore.exceptions")

    class _ClientError(Exception):
        pass

    fake_botocore_exceptions.ClientError = _ClientError
    fake_botocore.exceptions = fake_botocore_exceptions
    sys.modules["botocore"] = fake_botocore
    sys.modules["botocore.exceptions"] = fake_botocore_exceptions
    sys.modules["storage"] = types.SimpleNamespace(S3Storage=_FakeStorage)
    module = importlib.import_module("api")
    return importlib.reload(module)


def test_hub_resolve_and_policy_endpoints(tmp_path: Path) -> None:
    api_mod = _load_registry_api_module()
    settings = api_mod.RegistrySettings(
        db_path=str(tmp_path / "registry.sqlite"),
        s3_bucket="test-bucket",
    )
    app = api_mod.make_app(settings)
    client = TestClient(app)

    resolve = client.post("/v1/resolve", json={"uri": "oci://registry.local/team/demo@1.2.3"})
    assert resolve.status_code == HTTP_OK
    body = resolve.json()
    assert body["uri"].startswith("oci://")
    assert body["digest"].startswith("sha256:")
    assert isinstance(body["refs"], list)

    deny = client.post(
        "/v1/policy/evaluate",
        json={
            "context": {
                "source_uri": "oci://registry.local/team/demo@1.2.3",
                "trust_score": 0.4,
                "strict_failures": ["missing_or_invalid_signature"],
            },
            "policy": {
                "mode": "strict",
                "min_trust_score": 0.8,
                "allowed_sources": ["oci://registry.local/*"],
            },
        },
    )
    assert deny.status_code == HTTP_OK
    deny_payload = deny.json()
    assert deny_payload["allow"] is False
    assert deny_payload["decision"] == "deny"

    capabilities = client.get("/v1/capabilities")
    assert capabilities.status_code == HTTP_OK
    payload = capabilities.json()
    assert payload["verify"]["referrers_api"] is True

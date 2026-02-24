from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cpm_core.oci import OciClient, OciClientConfig, OciReferrer, build_artifact_spec
from cpm_core.oci.errors import OciCommandError, OciSecurityError
from cpm_core.oci.security import evaluate_trust_report, redact_command_for_log


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["oras"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_resolve_extracts_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*args, **kwargs):
        del args, kwargs
        return _completed(stdout="my-ref@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    digest = client.resolve("registry.local/team/pkg:1.0.0")
    assert digest == "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_push_falls_back_to_resolve_when_output_has_no_digest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    workdirs: list[str | None] = []

    def _fake_run(command, **kwargs):
        workdirs.append(kwargs.get("cwd"))
        calls.append(list(command))
        if command[1] == "push":
            return _completed(stdout="pushed")
        return _completed(stdout="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    file_path = tmp_path / "packet.manifest.json"
    file_path.write_text("{}", encoding="utf-8")

    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    result = client.push(
        "registry.local/project/repo:1.0.0",
        build_artifact_spec([file_path], {"packet.manifest.json": "application/vnd.cpm.packet.manifest.v1+json"}),
    )

    assert result.digest.endswith("b" * 64)
    assert len(calls) == 2
    assert calls[0][1] == "push"
    assert calls[1][1] == "resolve"
    assert workdirs[0] is not None
    assert str(file_path) not in " ".join(calls[0])


def test_pull_enforces_size_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_run(*args, **kwargs):
        del args, kwargs
        return _completed(stdout="sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    payload = out / "big.bin"
    payload.write_bytes(b"x" * 32)

    client = OciClient(
        OciClientConfig(
            allowlist_domains=("registry.local",),
            max_artifact_size_bytes=8,
        )
    )
    with pytest.raises(OciCommandError, match="exceeds configured limit"):
        client.pull("registry.local/team/pkg:1.0.0", out)


def test_allowlist_is_enforced() -> None:
    client = OciClient(OciClientConfig(allowlist_domains=("allowed.local",)))
    with pytest.raises(OciSecurityError):
        client.resolve("blocked.local/team/repo:1.0.0")


def test_missing_oras_returns_explicit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*args, **kwargs):
        del args, kwargs
        raise FileNotFoundError("oras")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient()
    with pytest.raises(OciCommandError, match="oras CLI not found"):
        client.resolve("registry.local/team/repo:1.0.0")


def test_redacts_sensitive_args() -> None:
    command = [
        "oras",
        "push",
        "registry.local/team/repo:1.0.0",
        "--username",
        "robot$build",
        "--password",
        "super-secret-password",
    ]
    redacted = redact_command_for_log(command)
    joined = " ".join(redacted)
    assert "super-secret-password" not in joined
    assert "***" in joined


def test_discover_referrers_parses_oras_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "manifests": [
            {
                "digest": "sha256:" + ("d" * 64),
                "artifactType": "application/vnd.dev.cosign.simplesigning.v1+json",
                "annotations": {"org.opencontainers.artifact.description": "cosign signature"},
            }
        ]
    }

    def _fake_run(command, **kwargs):
        del kwargs
        if command[1] == "discover":
            return _completed(stdout=json.dumps(payload))
        return _completed(stdout="[]")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    referrers = client.discover_referrers("registry.local/team/pkg@sha256:" + ("a" * 64))
    assert len(referrers) == 1
    assert referrers[0].artifact_type.startswith("application/vnd.dev.cosign")


def test_evaluate_trust_report_strict_fails_when_signature_missing() -> None:
    referrers = [
        OciReferrer(
            digest="sha256:" + ("e" * 64),
            artifact_type="application/spdx+json",
            annotations={"kind": "sbom"},
        )
    ]
    report = evaluate_trust_report(referrers, strict=True, require_signature=True, require_sbom=True)
    assert report.signature_valid is False
    assert "missing_or_invalid_signature" in report.strict_failures


def test_fetch_manifest_returns_json_document(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"schemaVersion": 2, "layers": []}

    def _fake_run(command, **kwargs):
        del kwargs
        assert command[:3] == ["oras", "manifest", "fetch"]
        return _completed(stdout=json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    manifest = client.fetch_manifest("registry.local/team/repo:1.0.0")
    assert manifest["schemaVersion"] == 2


def test_fetch_blob_returns_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(command, **kwargs):
        del kwargs
        assert command[:3] == ["oras", "blob", "fetch"]
        return _completed(stdout="{\"schema\":\"cpm.packet.metadata\"}")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    blob = client.fetch_blob("registry.local/team/repo:1.0.0", "sha256:" + ("f" * 64))
    assert b"cpm.packet.metadata" in blob


def test_fetch_blob_falls_back_to_single_arg_oras_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = "sha256:" + ("f" * 64)
    calls: list[list[str]] = []

    def _fake_run(command, **kwargs):
        del kwargs
        calls.append(list(command))
        if command[:5] == ["oras", "blob", "fetch", "registry.local/team/repo:1.0.0", digest]:
            return _completed(
                stderr=(
                    '"oras blob fetch" requires exactly 1 argument but got 2\n'
                    "Usage: oras blob fetch <name>@<digest>"
                ),
                returncode=1,
            )
        if command[:4] == ["oras", "blob", "fetch", f"registry.local/team/repo:1.0.0@{digest}"]:
            return _completed(stdout="{\"schema\":\"cpm.packet.metadata\"}")
        return _completed(stderr="unexpected command", returncode=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    blob = client.fetch_blob("registry.local/team/repo:1.0.0", digest)
    assert b"cpm.packet.metadata" in blob
    assert len(calls) >= 2
    assert calls[-1][:4] == ["oras", "blob", "fetch", f"registry.local/team/repo:1.0.0@{digest}"]


def test_fetch_blob_supports_oras_output_required_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = "sha256:" + ("e" * 64)

    def _fake_run(command, **kwargs):
        del kwargs
        if command[:5] == ["oras", "blob", "fetch", "registry.local/team/repo:1.0.0", digest]:
            return _completed(stderr='"oras blob fetch" requires exactly 1 argument but got 2', returncode=1)
        if command[:4] == ["oras", "blob", "fetch", f"registry.local/team/repo:1.0.0@{digest}"]:
            return _completed(stderr="either `--output` or `--descriptor` must be provided", returncode=1)
        if command[:4] == ["oras", "blob", "fetch", "--output"]:
            output = Path(command[4])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{\"schema\":\"cpm.packet.metadata\"}", encoding="utf-8")
            return _completed(stdout="")
        return _completed(stderr="unexpected command", returncode=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    client = OciClient(OciClientConfig(allowlist_domains=("registry.local",)))
    blob = client.fetch_blob("registry.local/team/repo:1.0.0", digest)
    assert b"cpm.packet.metadata" in blob

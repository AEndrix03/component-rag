from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cpm_core.oci import OciClient, OciClientConfig, build_artifact_spec
from cpm_core.oci.errors import OciCommandError, OciSecurityError
from cpm_core.oci.security import redact_command_for_log


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

    def _fake_run(command, **kwargs):
        del kwargs
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

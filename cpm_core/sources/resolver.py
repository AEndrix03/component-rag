from __future__ import annotations

import json
import tempfile
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from cpm_core.oci import OciClient, OciClientConfig
from cpm_core.oci.security import evaluate_trust_report

from .cache import SourceCache
from .models import LocalPacket, PacketReference, UpdateInfo


class CPMSource(Protocol):
    def can_handle(self, uri: str) -> bool: ...

    def resolve(self, uri: str) -> PacketReference: ...

    def fetch(self, ref: PacketReference, cache: SourceCache) -> LocalPacket: ...

    def check_updates(self, ref: PacketReference) -> UpdateInfo: ...


def _load_oci_config(workspace_root: Path) -> dict[str, object]:
    config_path = workspace_root / "config" / "config.toml"
    if not config_path.exists():
        return {}
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    section = payload.get("oci")
    return section if isinstance(section, dict) else {}


class OciSource:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def can_handle(self, uri: str) -> bool:
        return uri.startswith("oci://")

    def _client(self) -> OciClient:
        config = _load_oci_config(self.workspace_root)
        return OciClient(
            OciClientConfig(
                timeout_seconds=float(config.get("timeout_seconds", 30.0)),
                max_retries=int(config.get("max_retries", 2)),
                backoff_seconds=float(config.get("backoff_seconds", 0.2)),
                insecure=bool(config.get("insecure", False)),
                allowlist_domains=tuple(str(item) for item in config.get("allowlist_domains", []) if str(item).strip()),
                max_artifact_size_bytes=(
                    int(config["max_artifact_size_bytes"])
                    if config.get("max_artifact_size_bytes") is not None
                    else None
                ),
                username=str(config.get("username") or "").strip() or None,
                password=str(config.get("password") or "").strip() or None,
                token=str(config.get("token") or "").strip() or None,
            )
        )

    @staticmethod
    def _to_ref(uri: str) -> str:
        raw = uri[len("oci://") :].strip("/")
        if not raw:
            raise ValueError("invalid OCI source URI")
        if "@sha256:" in raw:
            return raw
        if "@" in raw:
            name, version = raw.split("@", 1)
            if not version:
                raise ValueError("invalid OCI source URI: missing version")
            return f"{name}:{version}"
        return raw

    def resolve(self, uri: str) -> PacketReference:
        ref = self._to_ref(uri)
        client = self._client()
        digest = client.resolve(ref)
        verification_cfg = _load_oci_config(self.workspace_root)
        strict = bool(verification_cfg.get("strict_verify", True))
        report = evaluate_trust_report(
            client.discover_referrers(f"{ref.split('@', 1)[0]}@{digest}"),
            strict=strict,
            require_signature=bool(verification_cfg.get("require_signature", True)),
            require_sbom=bool(verification_cfg.get("require_sbom", True)),
            require_provenance=bool(verification_cfg.get("require_provenance", True)),
        )
        if strict and report.strict_failures:
            failures = ",".join(report.strict_failures)
            raise ValueError(f"OCI source verification failed: {failures}")
        return PacketReference(
            uri=uri,
            resolved_uri=f"oci://{ref}",
            digest=digest,
            metadata={
                "source": "oci",
                "ref": ref,
                "trust_score": report.trust_score,
                "verification": asdict(report),
            },
        )

    def fetch(self, ref: PacketReference, cache: SourceCache) -> LocalPacket:
        client = self._client()
        with tempfile.TemporaryDirectory(prefix="cpm-source-oci-") as tmp:
            pull_dir = Path(tmp) / "artifact"
            client.pull(str(ref.metadata.get("ref") or ref.resolved_uri[len("oci://") :]), pull_dir)
            manifest_path = pull_dir / "packet.manifest.json"
            payload_root = "payload"
            if manifest_path.exists():
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                payload_root = str(payload.get("payload_root") or "payload").strip() or "payload"
            payload_dir = pull_dir / payload_root
            if not payload_dir.exists() or not payload_dir.is_dir():
                raise FileNotFoundError(f"OCI payload directory not found: {payload_dir}")
            return cache.materialize_directory(payload_dir, digest=ref.digest)

    def check_updates(self, ref: PacketReference) -> UpdateInfo:
        latest = self._client().resolve(str(ref.metadata.get("ref") or ref.resolved_uri[len("oci://") :]))
        return UpdateInfo(has_update=latest != ref.digest, latest_digest=latest)


class SourceResolver:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.cache = SourceCache(self.workspace_root)
        self._source: CPMSource = OciSource(self.workspace_root)

    def resolve_and_fetch(self, uri: str) -> tuple[PacketReference, LocalPacket]:
        if not self._source.can_handle(uri):
            raise ValueError("unsupported source URI: only oci:// is supported")
        reference = self._source.resolve(uri)
        packet = self._source.fetch(reference, self.cache)
        return reference, packet

from __future__ import annotations

import json
import tarfile
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

from cpm_core.oci import OciClient, OciClientConfig

from .cache import SourceCache, directory_digest
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


class DirSource:
    def can_handle(self, uri: str) -> bool:
        return uri.startswith("dir://") or Path(uri).exists()

    def resolve(self, uri: str) -> PacketReference:
        if uri.startswith("dir://"):
            target = Path(uri[len("dir://") :])
        else:
            target = Path(uri)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"source directory not found: {target}")
        digest = directory_digest(target.resolve())
        return PacketReference(
            uri=uri,
            resolved_uri=str(target.resolve()),
            digest=digest,
            metadata={"source": "dir"},
        )

    def fetch(self, ref: PacketReference, cache: SourceCache) -> LocalPacket:
        return cache.materialize_directory(Path(ref.resolved_uri), digest=ref.digest)

    def check_updates(self, ref: PacketReference) -> UpdateInfo:
        current = directory_digest(Path(ref.resolved_uri))
        return UpdateInfo(has_update=current != ref.digest, latest_digest=current)


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
        digest = self._client().resolve(ref)
        return PacketReference(
            uri=uri,
            resolved_uri=f"oci://{ref}",
            digest=digest,
            metadata={"source": "oci", "ref": ref},
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


class HubSource:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._oci = OciSource(workspace_root)
        self._dir = DirSource()

    def can_handle(self, uri: str) -> bool:
        return uri.startswith("https://") or uri.startswith("http://")

    def resolve(self, uri: str) -> PacketReference:
        parsed = urllib.parse.urlparse(uri)
        query = urllib.parse.parse_qs(parsed.query)
        nested_uri = (query.get("uri") or [None])[0]
        if nested_uri:
            endpoint = uri
            payload = json.dumps({"uri": nested_uri}).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=20) as response:  # nosec - controlled in tests/config
                body = response.read()
            result = json.loads(body.decode("utf-8"))
            resolved_uri = str(result.get("uri") or nested_uri)
            digest = str(result.get("digest") or "")
            if not digest:
                raise ValueError("hub resolve response missing digest")
            return PacketReference(
                uri=uri,
                resolved_uri=resolved_uri,
                digest=digest,
                metadata={"source": "hub", "mode": "resolve"},
            )
        return PacketReference(
            uri=uri,
            resolved_uri=uri,
            digest=uri,
            metadata={"source": "hub", "mode": "direct"},
        )

    def fetch(self, ref: PacketReference, cache: SourceCache) -> LocalPacket:
        resolved = ref.resolved_uri
        if resolved.startswith("oci://"):
            return self._oci.fetch(self._oci.resolve(resolved), cache)
        if resolved.startswith("dir://") or Path(resolved).exists():
            return self._dir.fetch(self._dir.resolve(resolved), cache)
        with tempfile.TemporaryDirectory(prefix="cpm-source-http-") as tmp:
            archive_path = Path(tmp) / "artifact.tar.gz"
            try:
                urllib.request.urlretrieve(resolved, archive_path)  # nosec - explicit user-provided URL
            except urllib.error.URLError as exc:
                raise RuntimeError(f"unable to download source archive: {exc}") from exc
            extract_dir = Path(tmp) / "payload"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive_path, mode="r:gz") as tar:
                tar.extractall(extract_dir)
            entries = [item for item in extract_dir.iterdir() if item.is_dir()]
            packet_dir = entries[0] if len(entries) == 1 else extract_dir
            return cache.materialize_directory(packet_dir, digest=ref.digest)

    def check_updates(self, ref: PacketReference) -> UpdateInfo:
        return UpdateInfo(has_update=False, detail="hub source update checks are not implemented")


class SourceResolver:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.cache = SourceCache(self.workspace_root)
        self._sources: list[CPMSource] = [
            DirSource(),
            OciSource(self.workspace_root),
            HubSource(self.workspace_root),
        ]

    def resolve_and_fetch(self, uri: str) -> tuple[PacketReference, LocalPacket]:
        source = self._select_source(uri)
        reference = source.resolve(uri)
        packet = source.fetch(reference, self.cache)
        return reference, packet

    def _select_source(self, uri: str) -> CPMSource:
        for source in self._sources:
            if source.can_handle(uri):
                return source
        raise ValueError(f"unsupported source URI: {uri}")

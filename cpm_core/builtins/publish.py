"""Builtin OCI publish command."""

from __future__ import annotations

import logging
import tempfile
import tomllib
from argparse import ArgumentParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cpm_core.api import cpmcommand
from cpm_core.oci import OciClient, OciClientConfig, OciError, build_artifact_spec, build_oci_layout, package_ref_for

from .commands import _WorkspaceAwareCommand

logger = logging.getLogger(__name__)


@cpmcommand(name="publish", group="cpm")
class PublishCommand(_WorkspaceAwareCommand):
    @classmethod
    def configure(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--workspace-dir", default=".", help="Workspace root directory")
        parser.add_argument("--from-dir", required=True, help="Packet directory to publish")
        parser.add_argument("--registry", help="OCI registry repository, e.g. harbor.local/project")
        parser.add_argument("--insecure", action="store_true", help="Allow insecure TLS for OCI operations")
        parser.add_argument("--no-embed", action="store_true", help="Publish packet without vectors/faiss artifacts")

    def run(self, argv: Any) -> int:
        workspace_root = self._resolve(getattr(argv, "workspace_dir", None))
        requested_packet_dir = str(getattr(argv, "from_dir", "") or "").strip()
        packet_dir = _resolve_packet_dir(requested_packet_dir, workspace_root)
        if packet_dir is None:
            requested_abs = Path(requested_packet_dir).resolve() if requested_packet_dir else Path.cwd()
            print(f"[cpm:publish] packet directory not found: {requested_abs}")
            return 1

        config = _load_oci_config(workspace_root)
        repository = _normalize_repository(str(getattr(argv, "registry", "") or config.get("repository") or ""))
        if not repository:
            print("[cpm:publish] missing OCI repository. Set --registry or [oci].repository in config.toml")
            return 1

        client = OciClient(
            OciClientConfig(
                timeout_seconds=float(config.get("timeout_seconds", 30.0)),
                max_retries=int(config.get("max_retries", 2)),
                backoff_seconds=float(config.get("backoff_seconds", 0.2)),
                insecure=bool(getattr(argv, "insecure", False) or config.get("insecure", False)),
                allowlist_domains=tuple(str(item) for item in config.get("allowlist_domains", []) if str(item).strip()),
                username=_string_or_none(config.get("username")),
                password=_string_or_none(config.get("password")),
                token=_string_or_none(config.get("token")),
            )
        )

        include_embeddings = not bool(getattr(argv, "no_embed", False))
        try:
            with tempfile.TemporaryDirectory(prefix="cpm-publish-") as tmp:
                layout = build_oci_layout(packet_dir, Path(tmp) / "staging", include_embeddings=include_embeddings)
                ref = package_ref_for(name=layout.packet_name, version=layout.packet_version, repository=repository)
                spec = build_artifact_spec(list(layout.files), media_types=layout.media_types)
                result = client.push(ref, spec)
                print(f"[cpm:publish] published {layout.packet_name}@{layout.packet_version}")
                print(f"[cpm:publish] ref={result.ref}")
                print(f"[cpm:publish] digest={result.digest}")
                if not include_embeddings:
                    print("[cpm:publish] mode=no-embed (vectors/faiss excluded)")
            return 0
        except OciError as exc:
            print(f"[cpm:publish] failed: {exc}")
            return 1
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("unexpected error while publishing packet")
            print(f"[cpm:publish] unexpected failure: {exc}")
            return 1


def _load_oci_config(workspace_root: Path) -> dict[str, Any]:
    config_path = workspace_root / "config" / "config.toml"
    if not config_path.exists():
        return {}
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    section = payload.get("oci")
    return section if isinstance(section, dict) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    data = str(value).strip()
    return data if data else None


def _normalize_repository(value: str) -> str:
    repository = value.strip().rstrip("/")
    if not repository:
        return ""
    if repository.startswith("oci://"):
        return repository[len("oci://") :].strip("/")
    if repository.startswith(("http://", "https://")):
        parsed = urlsplit(repository)
        host = parsed.netloc.strip("/")
        path = parsed.path.strip("/")
        if host and path:
            return f"{host}/{path}"
        if host:
            return host
    return repository


def _resolve_packet_dir(raw_path: str, workspace_root: Path) -> Path | None:
    requested = Path(raw_path).expanduser()
    direct_candidates: list[Path] = []
    if requested.is_absolute():
        direct_candidates.append(requested)
    else:
        direct_candidates.extend([(Path.cwd() / requested).resolve(), (workspace_root.parent / requested).resolve()])
    for candidate in direct_candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    packet_name = requested.name.strip()
    if not packet_name:
        return None
    dist_packet_root = (workspace_root.parent / "dist" / packet_name).resolve()
    if not dist_packet_root.is_dir():
        return None

    version_dirs = sorted(path for path in dist_packet_root.iterdir() if path.is_dir())
    if len(version_dirs) != 1:
        return None

    resolved = version_dirs[0]
    print(f"[cpm:publish] resolved --from-dir {raw_path} -> {resolved}")
    return resolved

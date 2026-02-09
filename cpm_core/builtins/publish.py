"""Builtin OCI publish command."""

from __future__ import annotations

import tempfile
import tomllib
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from cpm_core.api import cpmcommand
from cpm_core.oci import OciClient, OciClientConfig, build_artifact_spec, build_oci_layout, package_ref_for

from .commands import _WorkspaceAwareCommand


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
        packet_dir = Path(str(getattr(argv, "from_dir", ""))).resolve()
        if not packet_dir.exists():
            print(f"[cpm:publish] packet directory not found: {packet_dir}")
            return 1

        config = _load_oci_config(workspace_root)
        repository = str(getattr(argv, "registry", "") or config.get("repository") or "").strip()
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

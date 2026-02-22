"""Builtin OCI publish command."""

from __future__ import annotations

import logging
import tempfile
import tomllib
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

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
        parser.add_argument("--minimal", action="store_true", help="Publish only minimal payload (no docs, no embeddings)")
        parser.add_argument("--full", action="store_true", help="Publish full payload mode")
        parser.add_argument("--with-docs", action="store_true", help="Include docs.jsonl in artifact payload")
        parser.add_argument("--no-docs", action="store_true", help="Exclude docs.jsonl from artifact payload")
        parser.add_argument("--with-embeddings", action="store_true", help="Include vectors/faiss artifacts")
        parser.add_argument("--no-embeddings", action="store_true", help="Exclude vectors/faiss artifacts")

    def run(self, argv: Any) -> int:
        workspace_root = self._resolve(getattr(argv, "workspace_dir", None))
        requested_packet_dir = str(getattr(argv, "from_dir", "") or "").strip()
        packet_dir = _resolve_packet_dir(requested_packet_dir, workspace_root)
        if packet_dir is None:
            requested_abs = Path(requested_packet_dir).resolve() if requested_packet_dir else Path.cwd()
            print(
                "[cpm:publish] no packet found in --from-dir "
                f"{requested_abs} (manifest.json missing or ambiguous version directory)"
            )
            return 1

        config = _load_oci_config(workspace_root)
        try:
            repository = _normalize_repository(str(getattr(argv, "registry", "") or config.get("repository") or ""))
        except ValueError as exc:
            print(f"[cpm:publish] {exc}")
            return 1
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

        minimal_mode = bool(getattr(argv, "minimal", False))
        full_mode = bool(getattr(argv, "full", False))
        if minimal_mode and full_mode:
            print("[cpm:publish] --minimal and --full are mutually exclusive")
            return 1
        default_docs = not minimal_mode
        default_embeddings = not minimal_mode

        include_docs = default_docs
        if bool(getattr(argv, "with_docs", False)):
            include_docs = True
        if bool(getattr(argv, "no_docs", False)):
            include_docs = False

        include_embeddings = default_embeddings
        if bool(getattr(argv, "with_embeddings", False)):
            include_embeddings = True
        if bool(getattr(argv, "no_embeddings", False)):
            include_embeddings = False
        if bool(getattr(argv, "no_embed", False)):
            include_embeddings = False

        try:
            with tempfile.TemporaryDirectory(prefix="cpm-publish-") as tmp:
                layout = build_oci_layout(
                    packet_dir,
                    Path(tmp) / "staging",
                    include_embeddings=include_embeddings,
                    include_docs=include_docs,
                    minimal=minimal_mode,
                )
                ref = package_ref_for(name=layout.packet_name, version=layout.packet_version, repository=repository)
                spec = build_artifact_spec(list(layout.files), media_types=layout.media_types)
                result = client.push(ref, spec)
                print(f"[cpm:publish] published {layout.packet_name}@{layout.packet_version}")
                print(f"[cpm:publish] ref={result.ref}")
                print(f"[cpm:publish] digest={result.digest}")
                if minimal_mode:
                    print("[cpm:publish] mode=minimal (docs/vectors/faiss excluded)")
                elif not include_docs or not include_embeddings:
                    print(
                        "[cpm:publish] mode=custom "
                        f"(docs={'on' if include_docs else 'off'} embeddings={'on' if include_embeddings else 'off'})"
                    )
            return 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"[cpm:publish] failed: {exc}")
            return 1
        except OciError as exc:
            print(f"[cpm:publish] failed: {exc}")
            return 1
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.debug("unexpected error while publishing packet", exc_info=True)
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
        raise ValueError("HTTP(S) registry URLs are not supported; use OCI reference '<registry>/<repository>'")
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
            resolved = _resolve_single_version_dir(candidate)
            if resolved is not None:
                if resolved != candidate:
                    print(f"[cpm:publish] resolved --from-dir {raw_path} -> {resolved}")
                return resolved

    packet_name = requested.name.strip()
    if not packet_name:
        return None
    dist_packet_root = (workspace_root.parent / "dist" / packet_name).resolve()
    if not dist_packet_root.is_dir():
        return None

    version_dirs = sorted(path for path in dist_packet_root.iterdir() if path.is_dir())
    if len(version_dirs) != 1:
        return None

    resolved = _resolve_single_version_dir(version_dirs[0])
    if resolved is None:
        return None

    print(f"[cpm:publish] resolved --from-dir {raw_path} -> {resolved}")
    return resolved


def _resolve_single_version_dir(candidate: Path) -> Path | None:
    if _is_packet_dir(candidate):
        return candidate
    subdirs = sorted(path for path in candidate.iterdir() if path.is_dir())
    packet_dirs = [path for path in subdirs if _is_packet_dir(path)]
    if len(packet_dirs) == 1:
        return packet_dirs[0]
    return None


def _is_packet_dir(path: Path) -> bool:
    return (path / "manifest.json").exists()

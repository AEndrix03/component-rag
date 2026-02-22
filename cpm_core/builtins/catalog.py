"""Build and optionally publish packet catalog artifacts."""

from __future__ import annotations

import json
import tempfile
import tomllib
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from cpm_core.api import cpmcommand
from cpm_core.oci import (
    CPM_CATALOG_MEDIATYPE,
    OciClient,
    OciClientConfig,
    build_artifact_spec,
    write_catalog_jsonl,
)

from .commands import _WorkspaceAwareCommand


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


@cpmcommand(name="catalog", group="cpm")
class CatalogCommand(_WorkspaceAwareCommand):
    """Create a packet version catalog and optionally publish it as OCI artifact."""

    @classmethod
    def configure(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--workspace-dir", default=".", help="Workspace root directory")
        parser.add_argument("--packages-root", default="packages", help="Local packages root")
        parser.add_argument("--output", default="", help="Catalog output file (.jsonl)")
        parser.add_argument("--publish-ref", default="", help="Optional OCI ref to publish the catalog")
        parser.add_argument("--insecure", action="store_true", help="Allow insecure TLS for OCI operations")
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def run(self, argv: Any) -> int:
        workspace_root = self._resolve(getattr(argv, "workspace_dir", None))
        packages_root = Path(str(getattr(argv, "packages_root", "packages") or "packages"))
        if not packages_root.is_absolute():
            packages_root = workspace_root / packages_root
        entries = self._collect_catalog_entries(packages_root)
        output_raw = str(getattr(argv, "output", "") or "").strip()
        output_path = Path(output_raw) if output_raw else workspace_root / "cache" / "catalog" / "cpm-catalog.jsonl"
        if not output_path.is_absolute():
            output_path = workspace_root / output_path
        write_catalog_jsonl(output_path, entries)

        publish_ref = str(getattr(argv, "publish_ref", "") or "").strip()
        pushed_digest = None
        if publish_ref:
            cfg = _load_oci_config(workspace_root)
            client = OciClient(
                OciClientConfig(
                    timeout_seconds=float(cfg.get("timeout_seconds", 30.0)),
                    max_retries=int(cfg.get("max_retries", 2)),
                    backoff_seconds=float(cfg.get("backoff_seconds", 0.2)),
                    insecure=bool(getattr(argv, "insecure", False) or cfg.get("insecure", False)),
                    allowlist_domains=tuple(str(item) for item in cfg.get("allowlist_domains", []) if str(item).strip()),
                    username=str(cfg.get("username") or "").strip() or None,
                    password=str(cfg.get("password") or "").strip() or None,
                    token=str(cfg.get("token") or "").strip() or None,
                )
            )
            with tempfile.TemporaryDirectory(prefix="cpm-catalog-") as tmp:
                artifact = Path(tmp) / "cpm-catalog.jsonl"
                artifact.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
                spec = build_artifact_spec([artifact], media_types={artifact.name: CPM_CATALOG_MEDIATYPE})
                result = client.push(publish_ref, spec)
                pushed_digest = result.digest

        payload = {
            "ok": True,
            "count": len(entries),
            "output": str(output_path),
            "publish_ref": publish_ref or None,
            "publish_digest": pushed_digest,
        }
        if str(getattr(argv, "format", "text")) == "json":
            print(json.dumps(payload, indent=2))
            return 0
        print(f"[cpm:catalog] entries={len(entries)} output={output_path}")
        if publish_ref:
            print(f"[cpm:catalog] published ref={publish_ref} digest={pushed_digest}")
        return 0

    def _collect_catalog_entries(self, packages_root: Path) -> list[dict[str, Any]]:
        if not packages_root.exists() or not packages_root.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for name_dir in sorted(path for path in packages_root.iterdir() if path.is_dir()):
            for version_dir in sorted(path for path in name_dir.iterdir() if path.is_dir()):
                manifest_path = version_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
                cpm = manifest.get("cpm") if isinstance(manifest.get("cpm"), dict) else {}
                name = str(cpm.get("name") or name_dir.name)
                version = str(cpm.get("version") or version_dir.name)
                entries.append(
                    {
                        "name": name,
                        "version": version,
                        "tag": version,
                        "source_uri": f"oci://{name}:{version}",
                        "kind": cpm.get("kind"),
                        "entrypoints": cpm.get("entrypoints"),
                        "capabilities": cpm.get("capabilities"),
                    }
                )
        return entries

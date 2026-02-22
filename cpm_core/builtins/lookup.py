"""Built-in lookup command for inspecting built packet metadata."""

from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from cpm_builtin.packages.versions import version_key
from cpm_core.api import cpmcommand
from cpm_core.oci import CPM_CATALOG_MEDIATYPE, parse_catalog_jsonl
from cpm_core.sources.resolver import OciSource, SourceResolver

from .commands import _WorkspaceAwareCommand


def _read_simple_yml(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    except UnicodeDecodeError:
        lines = path.read_text(encoding="latin-1").splitlines()

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


@cpmcommand(name="lookup", group="cpm")
class LookupCommand(_WorkspaceAwareCommand):
    """List packets under a destination root with metadata and health status."""

    @classmethod
    def configure(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--workspace-dir", default=".", help="Workspace root directory")
        parser.add_argument("--source-uri", help="Remote OCI source URI to inspect (oci://repo/name[:tag|@version])")
        parser.add_argument("--registry", help="OCI repository base used with --name")
        parser.add_argument("--name", help="Packet name used with --registry")
        parser.add_argument("--version", help="Requested packet version tag")
        parser.add_argument("--alias", default="latest", help="Alias tag used when --version is not provided")
        parser.add_argument("--entrypoint", help="Filter remote lookup by entrypoint")
        parser.add_argument("--kind", help="Filter remote lookup by packet kind")
        parser.add_argument("--capability", action="append", default=[], help="Required capability (repeatable)")
        parser.add_argument("--os", dest="target_os", help="Target OS compatibility filter")
        parser.add_argument("--arch", help="Target architecture compatibility filter")
        parser.add_argument("--use-catalog", action="store_true", help="Resolve source URI from local catalog")
        parser.add_argument("--catalog-file", help="Local JSONL catalog path used with --use-catalog")
        parser.add_argument("--catalog-ref", help="OCI catalog ref (e.g. oci://repo/catalog:latest)")
        parser.add_argument(
            "--destination",
            default="packages",
            help="Installed packets root (default: ./packages under workspace, i.e. ./.cpm/packages from project root)",
        )
        parser.add_argument(
            "--all-versions",
            action="store_true",
            help="Include all versions per package (default: latest only)",
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def run(self, argv: Any) -> int:
        workspace_root = self._resolve(getattr(argv, "workspace_dir", None))
        self.workspace_root = workspace_root
        remote_source_uri = self._resolve_remote_source(argv, workspace_root)
        if remote_source_uri:
            return self._run_remote_lookup(argv=argv, workspace_root=workspace_root, source_uri=remote_source_uri)

        destination_raw = str(getattr(argv, "destination", "packages") or "packages")
        destination = Path(destination_raw)
        if not destination.is_absolute() and workspace_root.name == ".cpm":
            parts = destination.parts
            if len(parts) > 0 and parts[0] == ".cpm":
                destination = Path(*parts[1:]) if len(parts) > 1 else Path(".")
        root = destination if destination.is_absolute() else (workspace_root / destination)

        packets = self._collect_packets(root=root, include_all_versions=bool(getattr(argv, "all_versions", False)))
        if getattr(argv, "format", "text") == "json":
            print(json.dumps({"ok": True, "root": str(root), "count": len(packets), "packets": packets}, indent=2))
            return 0

        if not packets:
            print(f"[cpm:lookup] no installed packets found under {root}")
            return 0

        print(f"[cpm:lookup] root={root} installed_packets={len(packets)}")
        for item in packets:
            status = "ok" if item["is_valid"] else "incomplete"
            print(
                f"[cpm:lookup] {item['name']}@{item['version']} status={status} "
                f"docs={item['docs']} vectors={item['vectors']} description={item['description']}"
            )
            print(f"[cpm:lookup] path={item['path']}")
        return 0

    def _resolve_remote_source(self, argv: Any, workspace_root: Path) -> str | None:
        explicit = str(getattr(argv, "source_uri", "") or "").strip()
        if explicit:
            return explicit
        registry = str(getattr(argv, "registry", "") or "").strip().rstrip("/")
        name = str(getattr(argv, "name", "") or "").strip()
        if not registry or not name:
            return None
        version = str(getattr(argv, "version", "") or "").strip()
        alias = str(getattr(argv, "alias", "latest") or "latest").strip() or "latest"
        tag = version or alias
        source_uri = f"oci://{registry}/{name}:{tag}"
        if bool(getattr(argv, "use_catalog", False)):
            catalog = self._load_catalog(
                workspace_root=workspace_root,
                catalog_file=str(getattr(argv, "catalog_file", "") or "").strip(),
                catalog_ref=str(getattr(argv, "catalog_ref", "") or "").strip(),
            )
            if catalog:
                matched = self._select_from_catalog(catalog, name=name, requested_tag=tag)
                if matched:
                    return matched
        return source_uri

    def _load_catalog(self, *, workspace_root: Path, catalog_file: str, catalog_ref: str) -> list[dict[str, Any]]:
        if catalog_file:
            path = Path(catalog_file)
        else:
            path = workspace_root / "cache" / "catalog" / "cpm-catalog.jsonl"
        if not path.exists():
            if not catalog_ref:
                return []
            try:
                source = OciSource(workspace_root)
                client = source._client()  # noqa: SLF001 - intentional reuse of source config
                ref = source._to_ref(catalog_ref)  # noqa: SLF001 - consistent URI parsing
                manifest = client.fetch_manifest(ref)
                digest = self._select_catalog_digest(manifest)
                if not digest:
                    return []
                blob = client.fetch_blob(ref, digest)
                return parse_catalog_jsonl(blob.decode("utf-8"))
            except Exception:
                return []
        entries: list[dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def _select_catalog_digest(self, manifest_payload: dict[str, Any]) -> str | None:
        layers = manifest_payload.get("layers")
        if not isinstance(layers, list):
            return None
        fallback = None
        for item in layers:
            if not isinstance(item, dict):
                continue
            digest = str(item.get("digest") or "").strip()
            media_type = str(item.get("mediaType") or "").strip()
            if not fallback and digest:
                fallback = digest
            if media_type == CPM_CATALOG_MEDIATYPE and digest:
                return digest
        return fallback

    def _select_from_catalog(self, entries: list[dict[str, Any]], *, name: str, requested_tag: str) -> str | None:
        for item in entries:
            if str(item.get("name") or "") != name:
                continue
            if str(item.get("tag") or "") != requested_tag and str(item.get("version") or "") != requested_tag:
                continue
            uri = str(item.get("source_uri") or "").strip()
            if uri:
                return uri
        return None

    def _run_remote_lookup(self, *, argv: Any, workspace_root: Path, source_uri: str) -> int:
        resolver = SourceResolver(workspace_root)
        try:
            reference, metadata = resolver.lookup_metadata(source_uri)
        except Exception as exc:
            print(f"[cpm:lookup] failed remote lookup: {exc}")
            return 1

        packet = metadata.get("packet") if isinstance(metadata.get("packet"), dict) else {}
        compat = metadata.get("compat") if isinstance(metadata.get("compat"), dict) else {}
        entrypoints = packet.get("entrypoints") if isinstance(packet.get("entrypoints"), list) else []
        capabilities = packet.get("capabilities") if isinstance(packet.get("capabilities"), list) else []
        kind = str(packet.get("kind") or "")

        if str(getattr(argv, "kind", "") or "").strip() and str(getattr(argv, "kind", "")).strip() != kind:
            print(f"[cpm:lookup] no match: kind={getattr(argv, 'kind')}")
            return 1
        requested_caps = [str(item).strip() for item in list(getattr(argv, "capability", []) or []) if str(item).strip()]
        for capability in requested_caps:
            if capability not in [str(item) for item in capabilities]:
                print(f"[cpm:lookup] no match: missing capability={capability}")
                return 1
        requested_os = str(getattr(argv, "target_os", "") or "").strip()
        if requested_os:
            supported_os = compat.get("os") if isinstance(compat.get("os"), list) else []
            if supported_os and requested_os not in [str(item) for item in supported_os]:
                print(f"[cpm:lookup] no match: os={requested_os}")
                return 1
        requested_arch = str(getattr(argv, "arch", "") or "").strip()
        if requested_arch:
            supported_arch = compat.get("arch") if isinstance(compat.get("arch"), list) else []
            if supported_arch and requested_arch not in [str(item) for item in supported_arch]:
                print(f"[cpm:lookup] no match: arch={requested_arch}")
                return 1

        selected_entrypoint = None
        requested_entrypoint = str(getattr(argv, "entrypoint", "") or "").strip()
        if requested_entrypoint:
            for item in entrypoints:
                if isinstance(item, str) and item == requested_entrypoint:
                    selected_entrypoint = item
                    break
                if isinstance(item, dict) and str(item.get("name") or "") == requested_entrypoint:
                    selected_entrypoint = requested_entrypoint
                    break
            if selected_entrypoint is None:
                print(f"[cpm:lookup] no match: entrypoint={requested_entrypoint}")
                return 1
        elif entrypoints:
            first = entrypoints[0]
            selected_entrypoint = first if isinstance(first, str) else str(first.get("name") or "")

        resolved_ref = str(reference.metadata.get("ref") or "")
        digest_ref = resolved_ref.split("@", 1)[0]
        if ":" in digest_ref:
            digest_ref = digest_ref.rsplit(":", 1)[0]
        pinned_uri = f"oci://{digest_ref}@{reference.digest}"
        result = {
            "ok": True,
            "source_uri": source_uri,
            "resolved_uri": reference.resolved_uri,
            "digest": reference.digest,
            "pinned_uri": pinned_uri,
            "selected_entrypoint": selected_entrypoint,
            "packet": packet,
            "compat": compat,
            "metadata_digest": reference.metadata.get("metadata_digest"),
        }
        if getattr(argv, "format", "text") == "json":
            print(json.dumps(result, indent=2))
            return 0
        print(
            f"[cpm:lookup] remote {packet.get('name')}@{packet.get('version')} "
            f"digest={reference.digest} entrypoint={selected_entrypoint or '-'}"
        )
        print(f"[cpm:lookup] pinned={pinned_uri}")
        return 0

    def _collect_packets(self, *, root: Path, include_all_versions: bool) -> list[dict[str, Any]]:
        if not root.exists() or not root.is_dir():
            return []

        packets: list[dict[str, Any]] = []
        for name_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            versions = [path for path in name_dir.iterdir() if path.is_dir()]
            if not versions:
                continue
            versions.sort(key=lambda path: version_key(path.name))
            selected = versions if include_all_versions else [versions[-1]]
            for version_dir in selected:
                packets.append(self._packet_info(version_dir))

        packets.sort(key=lambda item: (str(item["name"]), version_key(str(item["version"]))))
        return packets

    def _packet_info(self, packet_dir: Path) -> dict[str, Any]:
        manifest_path = packet_dir / "manifest.json"
        cpm_yml_path = packet_dir / "cpm.yml"
        docs_path = packet_dir / "docs.jsonl"
        vectors_path = packet_dir / "vectors.f16.bin"
        faiss_path = packet_dir / "faiss" / "index.faiss"

        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        yml = _read_simple_yml(cpm_yml_path)
        cpm_meta = manifest.get("cpm") if isinstance(manifest.get("cpm"), dict) else {}
        counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}

        name = yml.get("name") or cpm_meta.get("name") or packet_dir.parent.name
        version = yml.get("version") or cpm_meta.get("version") or packet_dir.name
        if str(name).strip() == str(version).strip() and packet_dir.parent.name.strip() != str(name).strip():
            # Some older packets persisted the version into `name`; use directory layout as a safer display fallback.
            name = packet_dir.parent.name
        description = yml.get("description") or cpm_meta.get("description") or ""
        docs_count = counts.get("docs")
        vectors_count = counts.get("vectors")

        return {
            "name": str(name),
            "version": str(version),
            "description": str(description),
            "path": str(packet_dir.resolve()).replace("\\", "/"),
            "docs": int(docs_count) if isinstance(docs_count, int) else None,
            "vectors": int(vectors_count) if isinstance(vectors_count, int) else None,
            "is_valid": manifest_path.exists() and cpm_yml_path.exists() and docs_path.exists() and vectors_path.exists() and faiss_path.exists(),
        }

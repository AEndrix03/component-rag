import json
from pathlib import Path
from typing import Any, Dict, Optional, List


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _read_simple_yml(path: Path) -> Dict[str, str]:
    """
    Parser minimale per:
      key: value
    NO liste, NO nesting.
    """
    out: Dict[str, str] = {}
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
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _split_csv(v: Optional[str]) -> List[str]:
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def _extract_packet_info(packet_root: Path) -> Dict[str, Any]:
    manifest = _read_json(packet_root / "manifest.json") or {}
    yml = _read_simple_yml(packet_root / "cpm.yml")

    # prefer cpm.yml for "human" fields, fallback manifest/dir
    name = yml.get("name") or manifest.get("packet_id") or packet_root.name
    version = yml.get("version") or manifest.get("cpm", {}).get("version") or "unknown"
    description = yml.get("description") or ""
    tags = _split_csv(yml.get("tags"))
    entrypoints = _split_csv(yml.get("entrypoints"))

    embedding = manifest.get("embedding") or {}
    emb_model = yml.get("embedding_model") or embedding.get("model")
    emb_dim = yml.get("embedding_dim") or embedding.get("dim")
    emb_norm = yml.get("embedding_normalized")
    if emb_norm is None:
        emb_norm = embedding.get("normalized")

    counts = manifest.get("counts") or {}

    info: Dict[str, Any] = {
        "name": name,
        "version": version,
        "description": description,
        "tags": tags,
        "entrypoints": entrypoints,
        "dir_name": packet_root.name,
        "path": str(packet_root).replace("\\", "/"),
        "docs": counts.get("docs"),
        "vectors": counts.get("vectors"),
        "embedding_model": emb_model,
        "embedding_dim": emb_dim,
        "embedding_normalized": emb_norm,
        "has_faiss": (packet_root / "faiss" / "index.faiss").exists(),
        "has_docs": (packet_root / "docs.jsonl").exists(),
        "has_manifest": (packet_root / "manifest.json").exists(),
        "has_cpm_yml": (packet_root / "cpm.yml").exists(),
    }
    return info


def _iter_packet_dirs(cpm_dir: Path) -> List[Path]:
    if not cpm_dir.exists() or not cpm_dir.is_dir():
        return []
    out: List[Path] = []
    for p in sorted(cpm_dir.iterdir()):
        if not p.is_dir():
            continue
        if (p / "manifest.json").exists() or (p / "cpm.yml").exists() or (p / "faiss" / "index.faiss").exists():
            out.append(p)
    return out


def cmd_cpm_lookup(args) -> None:
    cpm_dir = Path(args.cpm_dir)
    packet_dirs = _iter_packet_dirs(cpm_dir)

    if not packet_dirs:
        print(f"[cpm:lookup] No packets found in: {cpm_dir.resolve()}")
        print("            - expected folders like .cpm/<name>/manifest.json or .cpm/<name>/cpm.yml")
        return

    infos = [_extract_packet_info(p) for p in packet_dirs]

    if args.format == "jsonl":
        for it in infos:
            print(json.dumps(it, ensure_ascii=False))
        return

    print(f"[cpm:lookup] packets={len(infos)} root={cpm_dir.resolve()}")
    for it in infos:
        name = it.get("name")
        version = it.get("version")
        docs = it.get("docs")
        model = it.get("embedding_model")
        dim = it.get("embedding_dim")
        eps = ",".join(it.get("entrypoints") or [])
        tags = ",".join(it.get("tags") or [])
        has_faiss = "yes" if it.get("has_faiss") else "no"

        print(f"- {name}  v={version}  docs={docs}  emb={model}({dim})  faiss={has_faiss}")
        if eps:
            print(f"  entrypoints={eps}")
        if tags:
            print(f"  tags={tags}")
        if it.get("description"):
            print(f"  desc={it['description']}")
        print(f"  path={it.get('path')}")

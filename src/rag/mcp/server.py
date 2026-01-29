from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# MCP (official python SDK)
# pip install mcp
from mcp.server.fastmcp import FastMCP


mcp = FastMCP(name="rag-cpm")


# ----------------------------
# Helpers (lookup)
# ----------------------------

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

    return {
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


# ----------------------------
# Helpers (query)
# ----------------------------

def _resolve_packet_dir(cpm_dir: Path, packet: str) -> Optional[Path]:
    packet_arg = Path(packet)
    if packet_arg.exists() and packet_arg.is_dir():
        return packet_arg

    candidate = cpm_dir / packet
    if candidate.exists() and candidate.is_dir():
        return candidate

    return None


def _load_docs(docs_path: Path) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    with docs_path.open("r", encoding="utf-8") as f:
        for line in f:
            docs.append(json.loads(line))
    return docs


def _query_packet(
    *,
    cpm_dir: Path,
    packet: str,
    query: str,
    k: int = 5,
    embed_url: Optional[str] = None,
) -> Dict[str, Any]:
    # Lazy imports: costosi
    import faiss  # type: ignore

    from rag.embedding.http_embedder import HttpEmbedder  # local import

    packet_dir = _resolve_packet_dir(cpm_dir, packet)
    if packet_dir is None:
        tried = (cpm_dir / packet).resolve()
        return {
            "ok": False,
            "error": "packet_not_found",
            "packet": packet,
            "tried": str(tried).replace("\\", "/"),
        }

    comp = packet_dir

    manifest = json.loads((comp / "manifest.json").read_text(encoding="utf-8"))
    model_name = manifest["embedding"]["model"]
    max_seq_length = int(manifest["embedding"].get("max_seq_length", 1024))

    docs = _load_docs(comp / "docs.jsonl")
    index = faiss.read_index(str(comp / "faiss" / "index.faiss"))

    if not embed_url:
        embed_url = os.environ.get("RAG_EMBED_URL", "http://127.0.0.1:8765")

    client = HttpEmbedder(embed_url)
    if not client.health():
        return {
            "ok": False,
            "error": "embed_server_unreachable",
            "embed_url": embed_url,
            "hint": "start it with: rag cpm embed start-server --detach (or set RAG_EMBED_URL)",
        }

    q = client.embed_texts(
        [query],
        model_name=model_name,
        max_seq_length=max_seq_length,
        normalize=True,
        dtype="float32",
        show_progress=False,
    )

    scores, ids = index.search(q, int(k))
    scores, ids = scores[0], ids[0]

    results: List[Dict[str, Any]] = []
    for idx, sc in zip(ids, scores):
        if int(idx) < 0:
            continue
        d = docs[int(idx)]
        results.append(
            {
                "score": float(sc),
                "id": d.get("id"),
                "text": d.get("text"),
                "metadata": d.get("metadata", {}),
            }
        )

    return {
        "ok": True,
        "packet": comp.name,
        "packet_path": str(comp).replace("\\", "/"),
        "query": query,
        "k": int(k),
        "embedding": {
            "model": model_name,
            "max_seq_length": max_seq_length,
            "embed_url": embed_url,
        },
        "results": results,
    }


# ----------------------------
# MCP Tools
# ----------------------------

@mcp.tool()
def lookup(cpm_dir: str | None = None) -> Dict[str, Any]:
    if not cpm_dir:
        cpm_dir = os.environ.get("RAG_CPM_DIR", ".cpm")

    """
    List installed context packets in a CPM folder (default: .cpm).

    Returns:
      { ok: bool, cpm_dir: str, packets: [ {name, version, ...} ] }
    """
    root = Path(cpm_dir)
    packet_dirs = _iter_packet_dirs(root)
    infos = [_extract_packet_info(p) for p in packet_dirs]
    return {
        "ok": True,
        "cpm_dir": str(root.resolve()).replace("\\", "/"),
        "packets": infos,
        "count": len(infos),
    }


@mcp.tool()
def query(
    packet: str,
    query: str,
    k: int = 5,
    cpm_dir: str | None = None,
    embed_url: Optional[str] = None,
) -> Dict[str, Any]:
    if not cpm_dir:
        cpm_dir = os.environ.get("RAG_CPM_DIR", ".cpm")

    """
    Query an installed packet by name/path under .cpm/ (FAISS + embedding server).

    Params:
      - packet: packet folder name under cpm_dir OR a direct path to a packet folder
      - query: text query
      - k: top-k
      - cpm_dir: CPM root (default: .cpm)
      - embed_url: override embedding server URL (default uses env RAG_EMBED_URL or http://127.0.0.1:8765)
    """
    return _query_packet(
        cpm_dir=Path(cpm_dir),
        packet=packet,
        query=query,
        k=k,
        embed_url=embed_url,
    )


def main() -> None:
    # stdio transport by default
    mcp.run()


if __name__ == "__main__":
    main()

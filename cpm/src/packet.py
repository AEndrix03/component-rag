import hashlib
import json
import os
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Iterable, Optional, Tuple

import numpy as np

from chunkers.base import ChunkingConfig
from chunkers.router import ChunkerRouter
from embedding.http_embedder import HttpEmbedder
from faiss_db import FaissFlatIP
from schema import Chunk

CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".cpp", ".c", ".h", ".cs"}
TEXT_EXTS = {".md", ".txt", ".rst"}


def iter_source_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (CODE_EXTS | TEXT_EXTS):
            yield p


def read_text_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


def _chunk_hash(text: str) -> str:
    # hash del contenuto (come richiesto)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_docs_jsonl(chunks: List[Chunk], out_path: Path) -> None:
    """
    Format per riga:
      {"id": ..., "text": ..., "hash": "...", "metadata": {...}}
    """
    with out_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            h = _chunk_hash(c.text)
            f.write(
                json.dumps(
                    {"id": c.id, "text": c.text, "hash": h, "metadata": c.metadata},
                    ensure_ascii=False,
                )
                + "\n"
            )


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksums(manifest: Dict[str, Any], out_root: Path) -> None:
    # checksum only large immutable artifacts (exclude manifest itself to avoid recursion)
    targets = [
        out_root / "cpm.yml",
        out_root / "docs.jsonl",
        out_root / "vectors.f16.bin",
        out_root / "faiss" / "index.faiss",
    ]
    checksums: Dict[str, Dict[str, str]] = {}
    for p in targets:
        if p.exists():
            rel = str(p.relative_to(out_root)).replace("\\", "/")
            checksums[rel] = {"algo": "sha256", "value": _sha256_file(p)}
    manifest["checksums"] = checksums


def _archive_packet_dir(out_root: Path, archive_format: str = "tar.gz") -> Path:
    # produce out_root.<ext> next to the folder (npm-like tarball)
    if archive_format not in ("tar.gz", "zip"):
        raise ValueError(f"Unsupported archive_format: {archive_format}")

    archive_path = Path(str(out_root) + (".tar.gz" if archive_format == "tar.gz" else ".zip"))
    if archive_path.exists():
        archive_path.unlink()

    if archive_format == "tar.gz":
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(out_root, arcname=out_root.name)
    else:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in out_root.rglob("*"):
                if p.is_file():
                    arcname = str(Path(out_root.name) / p.relative_to(out_root)).replace("\\", "/")
                    zf.write(p, arcname)
    return archive_path


def _infer_tags_from_ext_counts(ext_counts: Dict[str, int]) -> List[str]:
    """
    euristica: se troviamo certi ext, mettiamo tags.
    """
    tags: List[str] = []

    def has(ext: str) -> bool:
        return ext_counts.get(ext, 0) > 0

    # languages
    if has(".py"):
        tags.append("python")
    if has(".js"):
        tags.append("javascript")
    if has(".ts") or has(".tsx"):
        tags.append("typescript")
    if has(".java"):
        tags.append("java")
    if has(".kt"):
        tags.append("kotlin")
    if has(".go"):
        tags.append("go")
    if has(".rs"):
        tags.append("rust")
    if has(".cpp") or has(".c") or has(".h"):
        tags.append("cpp")
    if has(".cs"):
        tags.append("csharp")

    # docs-ish
    if has(".md") or has(".rst") or has(".txt"):
        tags.append("docs")

    # always tag as rag-component-ish
    tags.append("cpm")
    return sorted(set(tags))


def _write_cpm_yml(
        out_root: Path,
        *,
        name: str,
        version: str,
        description: str,
        tags: List[str],
        entrypoints: List[str],
        embedding_model: str,
        embedding_dim: int,
        embedding_normalized: bool,
) -> None:
    """
    YAML minimale (senza dipendenze). Valori sempre in forma semplice.
    """
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def esc(v: str) -> str:
        # stringa safe in YAML minimal: se contiene ":" o "#", mettiamo tra doppi apici
        if any(ch in v for ch in [":", "#", "\n", "\r", "\t"]):
            v = v.replace('"', '\\"')
            return f"\"{v}\""
        return v

    cpm_yml_path = out_root / "cpm.yml"
    with cpm_yml_path.open("w", encoding="utf-8") as f:
        f.write(f"cpm_schema: 1\n")
        f.write(f"name: {esc(name)}\n")
        f.write(f"version: {esc(version)}\n")
        f.write(f"description: {esc(description)}\n")
        f.write(f"tags: {esc(','.join(tags))}\n")
        f.write(f"entrypoints: {esc(','.join(entrypoints))}\n")
        f.write(f"embedding_model: {esc(embedding_model)}\n")
        f.write(f"embedding_dim: {int(embedding_dim)}\n")
        f.write(f"embedding_normalized: {'true' if embedding_normalized else 'false'}\n")
        f.write(f"created_at: {esc(created_at)}\n")

    print(f"[write] cpm.yml -> {cpm_yml_path}")


def _try_load_existing_cache(
        out_root: Path,
        *,
        model_name: str,
        max_seq_length: int,
) -> Optional[Tuple[Dict[str, np.ndarray], int]]:
    """
    Carica in RAM lo stato precedente (solo se compatibile) e ritorna:
      (cache_hash_to_vec_f32, dim)

    Policy conforme alla tua richiesta:
      - se una riga di docs.jsonl NON ha "hash", non la consideriamo cacheabile
        (quindi verrà re-embeddato se ricompare).
    """
    manifest_path = out_root / "manifest.json"
    docs_path = out_root / "docs.jsonl"
    vectors_path = out_root / "vectors.f16.bin"

    if not (manifest_path.exists() and docs_path.exists() and vectors_path.exists()):
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    emb = (manifest or {}).get("embedding") or {}
    prev_model = emb.get("model")
    prev_max_seq = emb.get("max_seq_length")
    prev_dim = emb.get("dim")

    # compatibilità minima (se cambia modello o max_seq_length, cache disabilitata)
    if prev_model != model_name or int(prev_max_seq or -1) != int(max_seq_length):
        return None
    if prev_dim is None:
        return None

    dim = int(prev_dim)

    # carico docs + prendo solo le righe con hash
    prev_hashes: List[str] = []
    try:
        with docs_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    return None
                h = obj.get("hash")
                if isinstance(h, str) and len(h) >= 32:
                    prev_hashes.append(h)
                else:
                    # hash mancante => NON cacheabile (come richiesto)
                    prev_hashes.append(None)  # placeholder
    except Exception:
        return None

    n_docs = len(prev_hashes)
    if n_docs == 0:
        return None

    # carico vectors f16 e reshape
    try:
        raw = np.fromfile(str(vectors_path), dtype=np.float16)
    except Exception:
        return None

    expected = n_docs * dim
    if raw.size != expected:
        # formato non consistente => cache disabilitata
        return None

    mat_f16 = raw.reshape((n_docs, dim))
    mat_f32 = mat_f16.astype(np.float32)

    cache: Dict[str, np.ndarray] = {}
    for i, h in enumerate(prev_hashes):
        if h is None:
            continue
        # se ci sono duplicati, teniamo il primo (ok per reuse)
        if h not in cache:
            cache[h] = mat_f32[i].copy()

    return cache, dim


def build_packet(
        input_dir: str,
        packet_dir: str,
        model_name: str = "jinaai/jina-embeddings-v2-base-code",
        max_seq_length: int = 1024,
        lines_per_chunk: int = 80,
        overlap_lines: int = 10,
        archive: bool = True,
        archive_format: str = "tar.gz",
        version: str = "0.0.0",
        timeout: float = None,
) -> None:
    in_root = Path(input_dir)
    out_root = Path(packet_dir)

    print(f"[build] input_dir  = {in_root.resolve()}")
    print(f"[build] output_dir = {out_root.resolve()}")

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "faiss").mkdir(parents=True, exist_ok=True)

    # 1) scan + chunk
    chunks: List[Chunk] = []
    n_files = 0

    exts = sorted(CODE_EXTS | TEXT_EXTS)
    print(f"[scan] indexing extensions: {exts}")

    ext_counts: Dict[str, int] = {}
    for file_path in iter_source_files(in_root):
        n_files += 1
        ext = file_path.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

        text = read_text_file(file_path)
        rel = str(file_path.relative_to(in_root)).replace("\\", "/")

        router = ChunkerRouter()
        cfg = ChunkingConfig(
            chunk_tokens=800,
            overlap_tokens=120,
            hard_cap_tokens=max_seq_length - 32,  # non sfori mai l'embedder
            mode="auto",
        )

        file_chunks = router.chunk(
            text=text,
            source_id=rel,
            ext=ext,
            config=cfg,
        )

        for c in file_chunks:
            c.metadata["path"] = rel
            c.metadata["ext"] = ext
        chunks.extend(file_chunks)

        if n_files <= 5:
            print(f"[scan] + {rel} -> {len(file_chunks)} chunks")

    print(f"[scan] files_indexed={n_files}")
    print(f"[scan] chunks_total={len(chunks)}")

    if len(chunks) == 0:
        print("[error] No chunks found.")
        print("        - check --input_dir path")
        print("        - ensure there are files with supported extensions")
        return

    # 2) incremental cache: carico (se possibile) lo stato precedente in RAM
    cache_pack = _try_load_existing_cache(out_root, model_name=model_name, max_seq_length=max_seq_length)
    cache_vecs_by_hash: Dict[str, np.ndarray] = {}
    cache_dim: Optional[int] = None
    if cache_pack is not None:
        cache_vecs_by_hash, cache_dim = cache_pack
        print(f"[cache] enabled: cached_vectors={len(cache_vecs_by_hash)} dim={cache_dim}")
    else:
        print("[cache] disabled (no compatible previous build found)")

    # 3) calcolo hash per i nuovi chunk + preparo riuso/embedding
    new_hashes: List[str] = []
    for c in chunks:
        new_hashes.append(_chunk_hash(c.text))

    new_set = set(new_hashes)
    prev_set = set(cache_vecs_by_hash.keys()) if cache_vecs_by_hash else set()

    removed = len(prev_set - new_set) if cache_vecs_by_hash else 0
    reused = sum(1 for h in new_hashes if h in cache_vecs_by_hash) if cache_vecs_by_hash else 0

    # hash mancanti sul file/cache => da embeddare
    to_embed_idx: List[int] = []
    to_embed_texts: List[str] = []
    for i, (c, h) in enumerate(zip(chunks, new_hashes)):
        if h not in cache_vecs_by_hash:
            to_embed_idx.append(i)
            to_embed_texts.append(c.text)

    print(f"[cache] new_chunks={len(chunks)} reused={reused} to_embed={len(to_embed_idx)} removed={removed}")

    # 4) embed SOLO ciò che manca (via HTTP embedding server) e costruisco il matrix finale in ordine chunk
    embed_url = os.environ.get("RAG_EMBED_URL", "http://127.0.0.1:8876")
    client = HttpEmbedder(embed_url, timeout_s=timeout)
    if not client.health():
        print(f"[error] embedding server not reachable at {embed_url}")
        print("        - start it with: embedpool pool start")
        print("        - or set RAG_EMBED_URL")
        return

    print(f"[embed] server={embed_url}")
    print(f"[embed] model={model_name} max_seq_length={max_seq_length}")

    # se cache_dim esiste, la usiamo come controllo di coerenza
    vecs_missing: Optional[np.ndarray] = None
    dim: Optional[int] = cache_dim

    if len(to_embed_texts) > 0:
        vecs_missing = client.embed_texts(
            to_embed_texts,
            model_name=model_name,
            max_seq_length=max_seq_length,
            normalize=True,
            dtype="float32",
            show_progress=True,
        )
        dim = int(vecs_missing.shape[1])
        print(f"[embed] missing_vectors shape={vecs_missing.shape} dtype={vecs_missing.dtype}")
    else:
        if dim is None:
            # caso improbabile: nessun chunk da embeddare ma cache_dim assente (cache off)
            # => forziamo embed di 1 chunk per ottenere dim
            vecs_missing = client.embed_texts(
                [chunks[0].text],
                model_name=model_name,
                max_seq_length=max_seq_length,
                normalize=True,
                dtype="float32",
                show_progress=False,
            )
            dim = int(vecs_missing.shape[1])
            to_embed_idx = [0]
            print(f"[embed] dim inferred by 1-shot: dim={dim}")

    assert dim is not None

    # se cache dim non coincide, disabilito riuso (sicurezza)
    if cache_dim is not None and int(cache_dim) != int(dim):
        print(f"[cache] dim mismatch: cache_dim={cache_dim} new_dim={dim} -> cache disabled")
        cache_vecs_by_hash = {}
        reused = 0
        # tutto da embeddare
        to_embed_idx = list(range(len(chunks)))
        to_embed_texts = [c.text for c in chunks]
        vecs_missing = client.embed_texts(
            to_embed_texts,
            model_name=model_name,
            max_seq_length=max_seq_length,
            normalize=True,
            dtype="float32",
            show_progress=True,
        )

    # matrix finale (float32 per faiss)
    final_vecs = np.empty((len(chunks), dim), dtype=np.float32)

    # riuso
    if cache_vecs_by_hash:
        for i, h in enumerate(new_hashes):
            v = cache_vecs_by_hash.get(h)
            if v is not None:
                final_vecs[i] = v

    # fill embed mancanti
    if len(to_embed_idx) > 0:
        assert vecs_missing is not None
        for j, i in enumerate(to_embed_idx):
            final_vecs[i] = vecs_missing[j]

    print(f"[embed] final vectors shape={final_vecs.shape} dtype={final_vecs.dtype}")

    # 5) write docs (con hash per riga)
    docs_path = out_root / "docs.jsonl"
    write_docs_jsonl(chunks, docs_path)
    print(f"[write] docs.jsonl -> {docs_path} ({len(chunks)} lines)")

    # 6) faiss index (ricostruito, ma embeddings riusati)
    db = FaissFlatIP(dim=int(dim))
    db.add(final_vecs)
    print(f"[faiss] ntotal={db.index.ntotal}")

    index_path = out_root / "faiss" / "index.faiss"
    db.save(str(index_path))
    print(f"[write] faiss/index.faiss -> {index_path}")

    # 7) save vectors f16 (allineati a docs.jsonl)
    vectors_path = out_root / "vectors.f16.bin"
    final_vecs.astype("float16").tofile(str(vectors_path))
    print(f"[write] vectors.f16.bin -> {vectors_path}")

    # 8) write cpm.yml (ora che sappiamo dim)
    tags = _infer_tags_from_ext_counts(ext_counts)
    name = out_root.name
    input_path = in_root.as_posix()
    description = f"Auto-built from {input_path}"
    entrypoints = ["query"]
    _write_cpm_yml(
        out_root,
        name=name,
        version=version,
        description=description,
        tags=tags,
        entrypoints=entrypoints,
        embedding_model=model_name,
        embedding_dim=int(dim),
        embedding_normalized=True,
    )

    # 9) manifest (aggiungo stats cache)
    manifest: Dict[str, Any] = {
        "schema_version": "1.0",
        "packet_id": out_root.name,
        "embedding": {
            "provider": "sentence-transformers",
            "model": model_name,
            "dim": int(dim),
            "dtype": "float16",
            "normalized": True,
            "max_seq_length": max_seq_length,
        },
        "similarity": {
            "space": "cosine",
            "index_type": "faiss.IndexFlatIP",
            "notes": "cosine via inner product on L2-normalized vectors",
        },
        "files": {
            "docs": "docs.jsonl",
            "vectors": {"path": "vectors.f16.bin", "format": "f16_rowmajor"},
            "index": {"path": "faiss/index.faiss", "format": "faiss"},
            "calibration": None,
        },
        "counts": {"docs": len(chunks), "vectors": int(db.index.ntotal)},
        "source": {
            "input_dir": str(in_root).replace("\\", "/"),
            "file_ext_counts": ext_counts,
        },
        "cpm": {
            "name": name,
            "version": version,
            "tags": tags,
            "entrypoints": entrypoints,
        },
        "incremental": {
            "enabled": bool(cache_pack is not None),
            "reused": int(reused),
            "embedded": int(len(to_embed_idx)),
            "removed": int(removed),
        },
    }
    _write_checksums(manifest, out_root)
    manifest_path = out_root / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[write] manifest.json -> {manifest_path}")

    # 10) archive
    if archive:
        archive_path = _archive_packet_dir(out_root, archive_format)
        print(f"[write] archive -> {archive_path}")

    print("[done] build ok")

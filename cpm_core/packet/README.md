# cpm_core/packet - Packet Data Structures

**Data models and I/O utilities for CPM context packets.**

This package defines the core data structures for context packets, including chunks, manifests, and FAISS index wrappers, plus utilities for reading/writing packet files.

---

## Quick Start

```python
from cpm_core.packet.models import DocChunk, PacketManifest, EmbeddingSpec
from cpm_core.packet.io import write_docs_jsonl, write_manifest
from cpm_core.packet.faiss_db import FaissFlatIP

# Create chunks
chunks = [
    DocChunk(id="doc:0", text="Content here", metadata={"path": "doc.md"}),
    DocChunk(id="doc:1", text="More content", metadata={"path": "doc.md"}),
]

# Write chunks
write_docs_jsonl(chunks, Path("docs.jsonl"))

# Create FAISS index
db = FaissFlatIP(dim=768)
db.add(vectors)  # np.ndarray shape (N, 768)
db.save("index.faiss")

# Create manifest
manifest = PacketManifest(
    schema_version="1.0",
    packet_id="my-packet",
    embedding=EmbeddingSpec(
        provider="sentence-transformers",
        model="model-name",
        dim=768,
        dtype="float16",
        normalized=True,
    ),
)
write_manifest(manifest, Path("manifest.json"))
```

---

## Data Models

### DocChunk

Represents a single document chunk.

```python
@dataclass
class DocChunk:
    id: str                         # Unique chunk ID ("path:index")
    text: str                       # Chunk content
    metadata: Dict[str, Any]        # Arbitrary metadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DocChunk":
        """Load from dictionary."""
```

**Example:**

```python
chunk = DocChunk(
    id="README.md:0",
    text="# Project Title\n\nDescription...",
    metadata={
        "path": "README.md",
        "ext": ".md",
        "line_start": 0,
        "line_end": 20,
    }
)

# Serialize
data = chunk.to_dict()

# Deserialize
loaded = DocChunk.from_dict(data)
```

---

### EmbeddingSpec

Describes the embedding model configuration.

```python
@dataclass(frozen=True)
class EmbeddingSpec:
    provider: str | None            # "sentence-transformers", "openai", etc.
    model: str                      # Model identifier
    dim: int                        # Embedding dimension
    dtype: str                      # "float16", "float32"
    normalized: bool                # Whether vectors are L2-normalized
    max_seq_length: int | None      # Maximum sequence length

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EmbeddingSpec":
        """Load from dictionary."""
```

**Example:**

```python
spec = EmbeddingSpec(
    provider="sentence-transformers",
    model="jinaai/jina-embeddings-v2-base-code",
    dim=768,
    dtype="float16",
    normalized=True,
    max_seq_length=1024,
)
```

---

### PacketManifest

Complete metadata for a context packet.

```python
@dataclass
class PacketManifest:
    schema_version: str             # Manifest schema version
    packet_id: str                  # Unique packet identifier
    embedding: EmbeddingSpec        # Embedding configuration

    # Optional fields
    similarity: Dict[str, Any]      # Similarity metric details
    files: Dict[str, Any]           # File paths and formats
    counts: Dict[str, int]          # Document/vector counts
    source: Dict[str, Any]          # Source metadata
    cpm: Dict[str, Any]             # CPM-specific metadata
    incremental: Dict[str, Any]     # Incremental build stats
    checksums: Dict[str, Any]       # File checksums
    extras: Dict[str, Any]          # Additional metadata

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PacketManifest":
        """Deserialize from dictionary."""
```

**Example:**

```python
manifest = PacketManifest(
    schema_version="1.0",
    packet_id="my-docs",
    embedding=EmbeddingSpec(
        provider="sentence-transformers",
        model="all-MiniLM-L6-v2",
        dim=384,
        dtype="float16",
        normalized=True,
    ),
    similarity={
        "space": "cosine",
        "index_type": "faiss.IndexFlatIP",
    },
    files={
        "docs": "docs.jsonl",
        "vectors": {"path": "vectors.f16.bin", "format": "f16_rowmajor"},
        "index": {"path": "faiss/index.faiss", "format": "faiss"},
    },
    counts={
        "docs": 250,
        "vectors": 250,
    },
    incremental={
        "enabled": True,
        "reused": 200,
        "embedded": 50,
        "removed": 10,
    },
)
```

---

## FAISS Index Wrapper

### FaissFlatIP

Wrapper for FAISS `IndexFlatIP` (Inner Product similarity).

```python
class FaissFlatIP:
    def __init__(self, dim: int):
        """
        Initialize index.

        Args:
            dim: Vector dimension
        """

    def add(self, vectors: np.ndarray) -> None:
        """
        Add vectors to index.

        Args:
            vectors: Shape (N, dim), dtype float32
        """

    def search(self, query_vec: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search for nearest neighbors.

        Args:
            query_vec: Shape (dim,) or (1, dim)
            k: Number of results

        Returns:
            (scores, ids): Both shape (k,)
        """

    def save(self, path: Path | str) -> None:
        """Save index to disk."""
```

**Usage:**

```python
from cpm_core.packet.faiss_db import FaissFlatIP
import numpy as np

# Create index
db = FaissFlatIP(dim=768)

# Add vectors
vectors = np.random.randn(1000, 768).astype(np.float32)
vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)  # Normalize
db.add(vectors)

# Search
query = np.random.randn(768).astype(np.float32)
query /= np.linalg.norm(query)
scores, ids = db.search(query, k=5)

print(f"Top 5 scores: {scores}")
print(f"Top 5 IDs: {ids}")

# Save
db.save("index.faiss")
```

---

## I/O Utilities

### Writing

```python
from cpm_core.packet.io import (
    write_docs_jsonl,
    write_vectors_f16,
    write_manifest,
    compute_checksums,
)

# Write chunks
chunks = [DocChunk(...), DocChunk(...)]
write_docs_jsonl(chunks, Path("docs.jsonl"))

# Write vectors (converts to float16)
vectors = np.random.randn(100, 768).astype(np.float32)
write_vectors_f16(vectors, Path("vectors.f16.bin"))

# Write manifest
manifest = PacketManifest(...)
write_manifest(manifest, Path("manifest.json"))

# Compute checksums
checksums = compute_checksums(
    root=Path("packet-dir"),
    relative_paths=["docs.jsonl", "vectors.f16.bin", "faiss/index.faiss"]
)
# Returns: {"docs.jsonl": {"algo": "sha256", "value": "..."}, ...}
```

### Reading

```python
from cpm_core.packet.io import (
    read_docs_jsonl,
    read_vectors_f16,
    load_manifest,
)

# Read chunks
chunks = read_docs_jsonl(Path("docs.jsonl"))

# Read vectors (converts from float16 to float32)
vectors = read_vectors_f16(Path("vectors.f16.bin"), dim=768)
# Returns: np.ndarray shape (N, 768), dtype float32

# Load manifest
manifest = load_manifest(Path("manifest.json"))
```

---

## Packet Directory Structure

A typical packet directory:

```
my-packet/
├── cpm.yml              # Human-readable metadata
├── manifest.json        # Machine-readable manifest
├── docs.jsonl           # Chunk data (one JSON object per line)
├── vectors.f16.bin      # Embeddings in float16 (binary)
└── faiss/
    └── index.faiss      # FAISS index
```

---

## Hash-Based Caching

The builder uses SHA-256 hashes of chunk text for incremental builds:

```python
from cpm_core.packet.io import _chunk_hash

text = "This is a chunk of text"
hash_value = _chunk_hash(text)
# Returns: "abc123..." (SHA-256 hex digest)
```

Hashes are stored in `docs.jsonl`:

```json
{"id": "doc:0", "text": "...", "hash": "abc123...", "metadata": {...}}
```

---

## See Also

- [cpm_core/build/README.md](../build/README.md) - Build system
- [cpm_builtin/README.md](../../cpm_builtin/README.md) - Built-in features

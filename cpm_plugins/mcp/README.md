# cpm_plugins/mcp - Model Context Protocol Plugin

**Expose CPM packets as MCP tools for Claude Desktop integration.**

The MCP plugin bridges CPM's context packet system with Anthropic's Model Context Protocol, enabling Claude Desktop to discover and query installed context packets via MCP tools.

---

## Quick Start

### Start MCP Server

```bash
cpm mcp:serve --cpm-dir .cpm --embed-url http://127.0.0.1:8876
```

### Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "cpm": {
      "command": "cpm",
      "args": ["mcp:serve"],
      "cwd": "/path/to/your/workspace",
      "env": {
        "RAG_CPM_DIR": ".cpm",
        "RAG_EMBED_URL": "http://127.0.0.1:8876"
      }
    }
  }
}
```

### Use in Claude

```
User: What packets are available?
Claude: [calls lookup tool]

User: Query python-stdlib for "file operations"
Claude: [calls query tool with packet="python-stdlib", query="file operations"]
```

---

## Architecture

```
cpm_plugins/mcp/
├── plugin.toml                    # Plugin manifest
├── cpm_mcp_plugin/
│   ├── __init__.py
│   ├── entrypoint.py              # Plugin entrypoint
│   ├── features.py                # MCPServeCommand
│   ├── server.py                  # FastMCP server & tools
│   ├── reader.py                  # PacketReader (metadata)
│   └── retriever.py               # PacketRetriever (FAISS search)
└── README.md
```

---

## Plugin Manifest

```toml
# cpm_plugins/mcp/plugin.toml
[plugin]
id = "mcp"
name = "CPM MCP Plugin"
version = "0.1.0"
group = "mcp"
entrypoint = "cpm_mcp_plugin.entrypoint:MCPEntrypoint"
requires_cpm = ">=0.1.0"
```

---

## Components

### MCPEntrypoint (`entrypoint.py`)

Plugin initialization:

```python
class MCPEntrypoint:
    """Initialize the MCP plugin by loading feature modules."""

    def init(self, ctx) -> None:
        self.context = ctx
        _ = features.MCPServeCommand  # Trigger registration
        _ = server  # Ensure FastMCP tools are registered
```

### MCPServeCommand (`features.py`)

CLI command to start the MCP server:

```python
@cpmcommand(name="serve", group="mcp")
class MCPServeCommand(CPMAbstractCommand):
    """Start the Model Context Protocol (MCP) server for CPM packets."""

    @classmethod
    def configure(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--cpm-dir",
            default=".cpm",
            help="Workspace root where context packets are installed.",
        )
        parser.add_argument(
            "--embed-url",
            help="Embedding server URL to expose to MCP clients.",
        )

    def run(self, argv: Sequence[str]) -> int:
        cpm_dir = getattr(argv, "cpm_dir", ".cpm")
        embed_url = getattr(argv, "embed_url", None)
        run_server(cpm_dir=cpm_dir, embed_url=embed_url)
        return 0
```

### MCP Server (`server.py`)

FastMCP server exposing `lookup` and `query` tools:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="context-packet-manager")

@mcp.tool()
def lookup(
    cpm_dir: str | None = None,
    include_all_versions: bool = False,
) -> dict[str, Any]:
    """
    List all installed context packets.

    Args:
        cpm_dir: CPM workspace directory (default: .cpm)
        include_all_versions: Include all versions or just active (default: False)

    Returns:
        Dictionary with packet metadata
    """
    reader = PacketReader(_resolve_cpm_dir(cpm_dir))
    packets = reader.list_packets(include_all_versions=include_all_versions)
    return {
        "ok": True,
        "cpm_dir": str(reader.root),
        "packets": packets,
        "count": len(packets),
    }

@mcp.tool()
def query(
    packet: str,
    query: str,
    k: int = 5,
    cpm_dir: str | None = None,
    embed_url: str | None = None,
) -> dict[str, Any]:
    """
    Query a context packet for relevant chunks.

    Args:
        packet: Name of the packet to query
        query: Query string
        k: Number of results to return (default: 5)
        cpm_dir: CPM workspace directory (default: .cpm)
        embed_url: Embedding server URL (default: RAG_EMBED_URL env var)

    Returns:
        Dictionary with search results
    """
    root = _resolve_cpm_dir(cpm_dir)
    retriever = PacketRetriever(root, packet, embed_url=embed_url)
    return retriever.retrieve(query, k)
```

### PacketReader (`reader.py`)

Reads packet metadata from workspace:

```python
class PacketReader:
    """Inspect packets inside a CPM workspace."""

    def __init__(self, cpm_dir: Path):
        self.root = cpm_dir

    def list_packets(self, *, include_all_versions: bool = False) -> list[dict[str, Any]]:
        """
        List installed packets.

        Args:
            include_all_versions: If True, return all versions; if False, return active only

        Returns:
            List of packet metadata dictionaries
        """
        if include_all_versions:
            dirs = self._iter_packet_dirs()
        else:
            dirs = self._current_packet_dirs()
        return [self._extract_packet_info(path) for path in dirs]

    def resolve_packet_dir(self, packet: str) -> Path | None:
        """
        Resolve packet name to directory.

        Resolution order:
        1. Absolute path (if exists)
        2. Pinned version (if set)
        3. Latest installed version

        Returns:
            Path to packet directory or None if not found
        """
        # ... resolution logic ...
```

**Packet Metadata:**

```python
{
    "name": "python-stdlib",
    "version": "1.2.0",
    "description": "Python standard library documentation",
    "tags": ["python", "stdlib"],
    "entrypoints": ["sys", "os", "pathlib"],
    "dir_name": "1.2.0",
    "path": ".cpm/packages/python-stdlib/1/2/0",
    "docs": 1234,
    "vectors": 1234,
    "embedding_model": "jinaai/jina-embeddings-v2-base-code",
    "embedding_dim": 768,
    "embedding_normalized": True,
    "has_faiss": True,
    "has_docs": True,
    "has_manifest": True,
    "has_cpm_yml": True,
}
```

### PacketRetriever (`retriever.py`)

FAISS-based semantic search:

```python
class PacketRetriever:
    """Retrieve nearest neighbors from a built packet."""

    def __init__(
        self,
        cpm_dir: Path,
        packet: str,
        *,
        embed_url: str | None = None,
    ) -> None:
        self.cpm_dir = cpm_dir
        self.packet = packet
        self._reader = PacketReader(cpm_dir)
        self.packet_dir = self._reader.resolve_packet_dir(packet)

        # Load manifest
        self.manifest = json.loads(
            (self.packet_dir / "manifest.json").read_text()
        )

        # Load FAISS index
        self.index = faiss.read_index(
            str(self.packet_dir / "faiss" / "index.faiss")
        )

        # Load document chunks
        self.docs = self._load_docs()

        # Embedding configuration
        self.embed_url = embed_url or os.getenv("RAG_EMBED_URL") or DEFAULT_EMBED_URL

    def retrieve(self, query: str, k: int) -> dict[str, Any]:
        """
        Retrieve top-k chunks for query.

        Args:
            query: Query string
            k: Number of results

        Returns:
            Dictionary with results
        """
        # Embed query
        embedder = HttpEmbedder(self.embed_url)
        vector = embedder.embed_texts([query], ...)

        # FAISS search
        scores, ids = self.index.search(vector, k)

        # Format results
        hits = []
        for idx, score in zip(ids[0], scores[0]):
            doc = self.docs[int(idx)]
            hits.append({
                "score": float(score),
                "id": doc["id"],
                "text": doc["text"],
                "metadata": doc["metadata"],
            })

        return {
            "ok": True,
            "packet": self.packet,
            "query": query,
            "k": k,
            "results": hits,
        }
```

---

## MCP Tools

### lookup Tool

Lists installed context packets.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cpm_dir` | string | `.cpm` | Workspace directory |
| `include_all_versions` | boolean | `false` | Include all versions or active only |

**Response:**

```json
{
  "ok": true,
  "cpm_dir": "/path/to/.cpm",
  "count": 3,
  "packets": [
    {
      "name": "python-stdlib",
      "version": "1.2.0",
      "description": "Python standard library documentation",
      "tags": ["python", "stdlib"],
      "path": ".cpm/packages/python-stdlib/1/2/0",
      "docs": 1234,
      "vectors": 1234,
      "embedding_model": "jinaai/jina-embeddings-v2-base-code",
      "embedding_dim": 768,
      "has_faiss": true
    },
    {
      "name": "react-docs",
      "version": "18.2.0",
      "path": ".cpm/packages/react-docs/18/2/0",
      "docs": 856,
      "vectors": 856
    }
  ]
}
```

### query Tool

Searches a packet for relevant chunks.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `packet` | string | required | Packet name to query |
| `query` | string | required | Query string |
| `k` | integer | `5` | Number of results |
| `cpm_dir` | string | `.cpm` | Workspace directory |
| `embed_url` | string | env var | Embedding server URL |

**Response (Success):**

```json
{
  "ok": true,
  "packet": "python-stdlib",
  "packet_path": ".cpm/packages/python-stdlib/1/2/0",
  "query": "file operations",
  "k": 5,
  "embedding": {
    "model": "jinaai/jina-embeddings-v2-base-code",
    "max_seq_length": 1024,
    "embed_url": "http://127.0.0.1:8876"
  },
  "results": [
    {
      "score": 0.89,
      "id": "os.py:python:function:open:42-67",
      "text": "def open(file, mode='r', ...):\n    \"\"\"Open a file...\"\"\"\n    ...",
      "metadata": {
        "kind": "symbol",
        "symbol": "open",
        "lang": "python",
        "line_start": 42
      }
    }
  ]
}
```

**Response (Error):**

```json
{
  "ok": false,
  "error": "packet_not_found",
  "packet": "unknown-packet",
  "tried": ".cpm/packages/unknown-packet"
}
```

```json
{
  "ok": false,
  "error": "embed_server_unreachable",
  "embed_url": "http://127.0.0.1:8876",
  "hint": "configure provider via cpm embed add ... --set-default"
}
```

---

## Usage Examples

### Example 1: Start Server

```bash
# Default configuration
cpm mcp:serve

# Custom CPM directory
cpm mcp:serve --cpm-dir /path/to/.cpm

# Custom embedding URL
cpm mcp:serve --embed-url http://localhost:9000
```

### Example 2: Claude Desktop Integration

**Configuration File:**

```json
{
  "mcpServers": {
    "cpm": {
      "command": "cpm",
      "args": ["mcp:serve"],
      "cwd": "/Users/username/projects/my-app",
      "env": {
        "RAG_CPM_DIR": ".cpm",
        "RAG_EMBED_URL": "http://127.0.0.1:8876"
      }
    }
  }
}
```

**Claude Interaction:**

```
User: What documentation packets do I have installed?

Claude: [Calls lookup tool]
You have 3 documentation packets:
1. python-stdlib v1.2.0 - Python standard library
2. react-docs v18.2.0 - React documentation
3. typescript-docs v5.0.0 - TypeScript documentation

User: Search react-docs for "useState hook examples"

Claude: [Calls query tool with packet="react-docs", query="useState hook examples", k=3]
I found these relevant sections about useState:

1. (Score: 0.92) "useState is a React Hook that lets you add state to functional components..."
2. (Score: 0.87) "Example: const [count, setCount] = useState(0)..."
3. (Score: 0.85) "Best practices for useState: keep state minimal..."
```

### Example 3: Programmatic Usage

```python
from cpm_plugins.mcp.cpm_mcp_plugin.reader import PacketReader
from cpm_plugins.mcp.cpm_mcp_plugin.retriever import PacketRetriever
from pathlib import Path

# List packets
reader = PacketReader(Path(".cpm"))
packets = reader.list_packets()
for packet in packets:
    print(f"{packet['name']} @ {packet['version']}")

# Query packet
retriever = PacketRetriever(
    Path(".cpm"),
    "python-stdlib",
    embed_url="http://127.0.0.1:8876",
)
results = retriever.retrieve("file operations", k=5)
for hit in results["results"]:
    print(f"[{hit['score']:.2f}] {hit['id']}")
    print(f"  {hit['text'][:100]}...")
```

---

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `RAG_CPM_DIR` | CPM workspace directory | `.cpm` |
| `RAG_EMBED_URL` | Embedding server URL | `http://127.0.0.1:8876` |

### Command-Line Arguments

```bash
cpm mcp:serve --help

Options:
  --cpm-dir TEXT     Workspace root where context packets are installed
  --embed-url TEXT   Embedding server URL to expose to MCP clients
```

---

## Claude Desktop Setup

### macOS

Configuration file: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cpm": {
      "command": "cpm",
      "args": ["mcp:serve"],
      "cwd": "/Users/username/workspace",
      "env": {
        "RAG_CPM_DIR": ".cpm"
      }
    }
  }
}
```

### Windows

Configuration file: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cpm": {
      "command": "cpm.exe",
      "args": ["mcp:serve"],
      "cwd": "C:\\Users\\username\\workspace",
      "env": {
        "RAG_CPM_DIR": ".cpm"
      }
    }
  }
}
```

### Linux

Configuration file: `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cpm": {
      "command": "cpm",
      "args": ["mcp:serve"],
      "cwd": "/home/username/workspace",
      "env": {
        "RAG_CPM_DIR": ".cpm"
      }
    }
  }
}
```

---

## Transport Mode

The MCP plugin uses **stdio** transport for Claude Desktop:

- **Input**: stdin (JSON-RPC requests from Claude Desktop)
- **Output**: stdout (JSON-RPC responses to Claude Desktop)
- **Logging**: stderr (plugin logs)

This enables Claude Desktop to launch the MCP server as a subprocess and communicate via standard I/O.

---

## Error Handling

### Packet Not Found

```json
{
  "ok": false,
  "error": "packet_not_found",
  "packet": "unknown-pkg",
  "tried": ".cpm/packages/unknown-pkg"
}
```

**Solution:** Install the packet or check the name.

### Embed Server Unreachable

```json
{
  "ok": false,
  "error": "embed_server_unreachable",
  "embed_url": "http://127.0.0.1:8876",
  "hint": "configure provider via cpm embed add ... --set-default"
}
```

**Solution:** Start the embedding server.

### Retrieval Failed

```json
{
  "ok": false,
  "error": "retrieval_failed",
  "detail": "FAISS index corrupted"
}
```

**Solution:** Rebuild the packet.

---

## Performance Tips

1. **Start embedding server before querying**: Reduces cold-start latency
2. **Use pinned versions**: Ensures consistent query results
3. **Keep k <= 10**: Higher k increases response time
4. **Enable FAISS GPU** (optional): Faster search for large indexes

---

## Debugging

### Enable Debug Logging

```bash
export CPM_LOG_LEVEL=DEBUG
cpm mcp:serve
```

### Test Tools Directly

```python
from cpm_plugins.mcp.cpm_mcp_plugin.server import lookup, query

# Test lookup
result = lookup(cpm_dir=".cpm", include_all_versions=False)
print(result)

# Test query
result = query(
    packet="python-stdlib",
    query="file operations",
    k=5,
    cpm_dir=".cpm",
)
print(result)
```

### Check Claude Desktop Logs

```bash
# macOS
tail -f ~/Library/Logs/Claude/mcp*.log

# Windows
type %APPDATA%\Claude\Logs\mcp*.log

# Linux
tail -f ~/.local/share/claude/logs/mcp*.log
```

---

## Testing

```bash
# Run MCP plugin tests
pytest cpm_plugins/mcp/

# Test reader
pytest cpm_plugins/mcp/test_reader.py -v

# Test retriever
pytest cpm_plugins/mcp/test_retriever.py -v
```

---

## See Also

- [cpm_plugins/README.md](../README.md) - Plugin system overview
- [cpm_builtin/packages/README.md](../../cpm_builtin/packages/README.md) - Package management
- [cpm_core/packet/README.md](../../cpm_core/packet/README.md) - Packet structure
- [MCP Documentation](https://modelcontextprotocol.io/) - Model Context Protocol specification

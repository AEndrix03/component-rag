# cpm_builtin/chunking - Language-Aware Chunking Strategies

**Adaptive chunking system for code and documentation with hierarchical support.**

The chunking system provides multiple specialized strategies for breaking down source code and documentation into semantically meaningful chunks optimized for RAG applications. Each chunker preserves structural boundaries (functions, classes, sections) while respecting token budgets.

---

## Quick Start

```python
from cpm_builtin.chunking.router import ChunkerRouter
from cpm_builtin.chunking.base import ChunkingConfig

router = ChunkerRouter()
config = ChunkingConfig(
    chunk_tokens=800,
    overlap_tokens=120,
    hierarchical=True,
)

# Automatically selects the best chunker for .py files
chunks = router.chunk(
    text=source_code,
    source_id="main.py",
    ext=".py",
    config=config,
)

for chunk in chunks:
    print(f"{chunk.id}: {len(chunk.text)} chars")
    print(f"  Metadata: {chunk.metadata}")
```

---

## Architecture Overview

```
cpm_builtin/chunking/
├── base.py                 # ChunkingConfig, BaseChunker protocol
├── schema.py               # Chunk data model
├── router.py               # ChunkerRouter (auto/multi mode)
├── token_budget.py         # TokenBudgeter (packing + hierarchical splitting)
├── python_ast.py           # Python AST-based chunker
├── java.py                 # Java structure-aware chunker
├── markdown.py             # Markdown header-hierarchy chunker
├── text.py                 # Token-budget text chunker
├── treesitter_generic.py   # Tree-sitter for 40+ languages
└── brace_fallback.py       # Brace-based fallback for C-style languages
```

---

## Core Concepts

### ChunkingConfig

Centralized configuration for all chunking strategies:

```python
@dataclass(frozen=True)
class ChunkingConfig:
    # Token budgets
    chunk_tokens: int = 800              # Target chunk size
    overlap_tokens: int = 120            # Overlap between chunks
    hard_cap_tokens: int | None = None   # Maximum chunk size (embedder limit)

    # Context preservation
    include_source_preamble: bool = True              # Add imports/headers
    include_context_in_children: bool = True          # Inject context into children
    max_header_chars: int = 6000                      # Safety cap for headers

    # Code-specific packing
    max_symbol_blocks_per_chunk: int = 1              # Symbols per chunk
    separate_preamble_chunk: bool = True              # Separate preamble

    # Routing
    mode: str = "auto"                                # "auto" | "multi"
    multi_chunkers: list[str] | None = None           # For multi mode

    # Hierarchical chunking (NEW)
    hierarchical: bool = True                         # Enable parent/child structure
    micro_chunk_tokens: int = 220                     # Child chunk size
    micro_overlap_tokens: int = 40                    # Child overlap
    emit_parent_chunks: bool = False                  # Only emit children (FAISS-friendly)
    parent_level_name: str = "parent"
    child_level_name: str = "child"
    micro_split_strategy: str = "lines"               # "lines" | "paragraphs"
```

**Key Features:**

- **Hierarchical chunking**: Creates parent chunks (functions/sections) then splits them into smaller child chunks
- **Context injection**: Prepends headers/imports to child chunks for better retrieval
- **FAISS-friendly**: Option to emit only child chunks (more uniform sizes)
- **Token budgeting**: Respects embedder limits while maximizing semantic coherence

---

## ChunkerRouter

Automatically selects the best chunker based on file extension:

```python
from cpm_builtin.chunking.router import ChunkerRouter

router = ChunkerRouter()

# Auto mode (default) - picks best chunker per extension
chunks = router.chunk(
    text=code,
    source_id="app.js",
    ext=".js",
    config=config,
)

# Multi mode - runs multiple chunkers and merges results
config_multi = ChunkingConfig(
    mode="multi",
    multi_chunkers=["treesitter", "brace", "text"],
)
chunks = router.chunk(
    text=code,
    source_id="app.js",
    ext=".js",
    config=config_multi,
)
```

**Extension Mapping (40+ languages):**

| Extension | Chunker | Approach |
|-----------|---------|----------|
| `.py` | python_ast | Python AST parsing |
| `.java` | java | Java structure analysis |
| `.md` | markdown | Header hierarchy |
| `.txt`, `.rst` | text | Token-budget line packing |
| `.js`, `.jsx`, `.ts`, `.tsx` | treesitter | Tree-sitter parsing |
| `.go`, `.rs`, `.c`, `.cpp` | treesitter | Tree-sitter parsing |
| `.cs`, `.php`, `.rb`, `.kt` | treesitter | Tree-sitter parsing |
| `.swift`, `.html`, `.css` | treesitter | Tree-sitter parsing |
| `.json`, `.yaml`, `.xml` | treesitter | Tree-sitter parsing |
| Others | text | Fallback |

**Available Methods:**

```python
router.get_available_chunkers()  # ["treesitter", "java", "python_ast", ...]
router.get_chunker("python_ast")  # Get specific chunker instance
```

---

## Chunking Strategies

### Python AST Chunker (`python_ast.py`)

Parses Python code using the AST module and chunks by top-level definitions:

```python
from cpm_builtin.chunking.python_ast import PythonAstChunker

chunker = PythonAstChunker()
chunks = chunker.chunk(text, "module.py", ext=".py", config=config)
```

**Features:**

- Extracts import statements as preamble
- Identifies functions (including async) and classes
- Hierarchical splitting: function/class -> smaller child chunks
- Context injection: adds imports to child chunks
- Fallback to text chunker on parse errors

**Metadata:**

```python
{
    "kind": "symbol",           # or "symbol_child", "preamble"
    "node_type": "function",    # or "class"
    "symbol": "process_data",
    "lang": "python",
    "line_start": 42,
    "line_end": 67,
    "level": "parent",          # or "child"
    "parent_id": "module.py:python:function:process_data:42-67",
    "child_index": 0,           # for children
}
```

---

### Java Chunker (`java.py`)

Structure-aware chunker for Java code:

```python
from cpm_builtin.chunking.java import JavaChunker

chunker = JavaChunker()
chunks = chunker.chunk(text, "App.java", ext=".java", config=config)
```

**Features:**

- Extracts package and import declarations as preamble
- Identifies classes, interfaces, enums, methods
- Hierarchical splitting within methods
- Context injection for child chunks

**Metadata:**

```python
{
    "kind": "symbol",
    "node_type": "method",      # or "class", "interface", "enum"
    "symbol": "calculateTotal",
    "lang": "java",
    "line_start": 15,
    "line_end": 32,
}
```

---

### Markdown Chunker (`markdown.py`)

Preserves document structure by splitting on headers:

```python
from cpm_builtin.chunking.markdown import MarkdownChunker

chunker = MarkdownChunker()
chunks = chunker.chunk(text, "README.md", ext=".md", config=config)
```

**Features:**

- Uses mistune for AST parsing (fallback to regex)
- Treats each top-level section as parent chunk
- Hierarchical splitting within sections
- Preserves header titles in metadata

**Metadata:**

```python
{
    "kind": "section",          # or "section_child"
    "node_type": "heading",
    "title": "## Installation",
    "lang": "markdown",
    "level": "parent",
}
```

---

### Text Chunker (`text.py`)

Simple token-budget chunker for plain text:

```python
from cpm_builtin.chunking.text import TextChunker

chunker = TextChunker()
chunks = chunker.chunk(text, "notes.txt", ext=".txt", config=config)
```

**Features:**

- Packs lines or paragraphs into chunks
- Respects token budget and overlap
- No structural parsing
- Strategy: "lines" (robust) or "paragraphs" (prose)

**Metadata:**

```python
{
    "kind": "text",
    "lang": "text",
    "chunker": "text",
}
```

---

### Tree-Sitter Generic Chunker (`treesitter_generic.py`)

Universal chunker supporting 40+ languages via tree-sitter:

```python
from cpm_builtin.chunking.treesitter_generic import TreeSitterGenericChunker

chunker = TreeSitterGenericChunker()
chunks = chunker.chunk(text, "app.ts", ext=".ts", config=config)
```

**Supported Languages:**

- JavaScript, TypeScript, TSX
- Go, Rust, C, C++, C#
- PHP, Ruby, Kotlin, Swift
- HTML, CSS, SCSS
- JSON, YAML, XML

**Features:**

- Extracts import/package statements as preamble
- Identifies language-specific nodes (functions, classes, interfaces)
- Falls back to line-based chunking on parse errors
- Hierarchical splitting within symbols

**Interesting Nodes by Language:**

```python
INTERESTING_NODES = {
    "python": {"function_definition", "class_definition"},
    "typescript": {"function_declaration", "class_declaration", "interface_declaration"},
    "java": {"class_declaration", "method_declaration"},
    "go": {"function_declaration", "type_declaration"},
    "rust": {"function_item", "impl_item", "struct_item"},
}
```

---

### Brace Fallback Chunker (`brace_fallback.py`)

Simple brace-based chunker for C-style languages when tree-sitter fails:

```python
from cpm_builtin.chunking.brace_fallback import BraceFallbackChunker

chunker = BraceFallbackChunker()
chunks = chunker.chunk(text, "app.c", ext=".c", config=config)
```

**Features:**

- Detects top-level braced blocks
- Minimal parsing (regex-based)
- Useful as last resort

---

## Token Budget System

The `TokenBudgeter` class handles packing logical blocks into chunks:

```python
from cpm_builtin.chunking.token_budget import TokenBudgeter, Block

budgeter = TokenBudgeter()

# Create logical blocks
blocks = [
    Block(text="import sys\nimport os", meta={"kind": "preamble"}),
    Block(text="def main():\n    ...", meta={"kind": "symbol", "symbol": "main"}),
]

# Pack into chunks with overlap
chunks = budgeter.pack_blocks(
    blocks,
    source_id="script.py",
    base_meta={"lang": "python"},
    chunk_tokens=800,
    overlap_tokens=120,
    max_symbol_blocks_per_chunk=1,
    chunk_id_prefix="python_ast",
)
```

**Hierarchical Splitting:**

```python
# Split a large text into micro-chunks
parts = budgeter.split_text_micro(
    text=function_body,
    target_tokens=220,
    overlap_tokens=40,
    hard_cap_tokens=512,
    strategy="lines",  # or "paragraphs"
)
```

**Features:**

- Respects token budgets with overlap
- Enforces max symbols per chunk
- Hard-caps oversized blocks by line splitting
- Micro-splitting for hierarchical chunking

---

## Hierarchical Chunking

Hierarchical chunking creates two-level structure: parent chunks (functions, sections) and child chunks (smaller pieces):

```python
config = ChunkingConfig(
    chunk_tokens=800,
    overlap_tokens=120,
    hierarchical=True,              # Enable hierarchical mode
    micro_chunk_tokens=220,         # Child chunk size
    micro_overlap_tokens=40,        # Child overlap
    emit_parent_chunks=False,       # Only emit children (FAISS-friendly)
    include_context_in_children=True,  # Inject preamble into children
)

chunks = router.chunk(text, source_id, ext=".py", config=config)
```

**Example Output:**

```python
# Input: Python function (1200 tokens)
def process_data(data):
    """Process the input data."""
    # ... 50 lines of code ...

# Output: 6 child chunks (200-240 tokens each)
[
    Chunk(
        id="script.py:python:function:process_data:10-60:child:0",
        text="import sys\n\ndef process_data(data):\n    ...",  # With preamble
        metadata={
            "kind": "symbol_child",
            "level": "child",
            "parent_id": "script.py:python:function:process_data:10-60",
            "child_index": 0,
        }
    ),
    # ... 5 more children ...
]
```

**Benefits:**

- More uniform chunk sizes (better for FAISS)
- Context injection improves retrieval quality
- Parent metadata preserved in children
- Configurable parent/child emission

---

## Usage Examples

### Example 1: Basic Chunking

```python
from cpm_builtin.chunking.router import ChunkerRouter
from cpm_builtin.chunking.base import ChunkingConfig

router = ChunkerRouter()
config = ChunkingConfig(chunk_tokens=800, overlap_tokens=120)

with open("main.py") as f:
    code = f.read()

chunks = router.chunk(code, "main.py", ext=".py", config=config)

for chunk in chunks:
    print(f"Chunk {chunk.id}:")
    print(f"  Text: {chunk.text[:100]}...")
    print(f"  Metadata: {chunk.metadata}")
```

### Example 2: Multi-Chunker Mode

```python
config = ChunkingConfig(
    mode="multi",
    multi_chunkers=["python_ast", "treesitter", "text"],
)

chunks = router.chunk(code, "app.py", ext=".py", config=config)
# Returns deduplicated chunks from all three chunkers
```

### Example 3: Hierarchical with Context Injection

```python
config = ChunkingConfig(
    hierarchical=True,
    micro_chunk_tokens=220,
    emit_parent_chunks=False,
    include_source_preamble=True,
    include_context_in_children=True,
)

chunks = router.chunk(code, "module.py", ext=".py", config=config)

# All chunks are children with injected import context
for chunk in chunks:
    assert chunk.metadata["level"] == "child"
    assert "import" in chunk.text  # Context injected
```

### Example 4: Direct Chunker Usage

```python
from cpm_builtin.chunking.python_ast import PythonAstChunker

chunker = PythonAstChunker()
config = ChunkingConfig(chunk_tokens=800)

chunks = chunker.chunk(
    text=python_code,
    source_id="script.py",
    ext=".py",
    config=config,
)
```

---

## Configuration Guidelines

### For Code (Functions/Classes)

```python
ChunkingConfig(
    chunk_tokens=800,
    overlap_tokens=120,
    hierarchical=True,
    micro_chunk_tokens=220,
    emit_parent_chunks=False,
    max_symbol_blocks_per_chunk=1,  # One function per parent
    include_source_preamble=True,
    include_context_in_children=True,
)
```

### For Documentation (Markdown)

```python
ChunkingConfig(
    chunk_tokens=1200,              # Larger chunks for prose
    overlap_tokens=200,
    hierarchical=True,
    micro_chunk_tokens=400,
    emit_parent_chunks=True,        # Both parent and children
    micro_split_strategy="paragraphs",  # Better for text
)
```

### For Plain Text

```python
ChunkingConfig(
    chunk_tokens=800,
    overlap_tokens=120,
    hierarchical=False,             # Disable hierarchical
    mode="auto",
)
```

---

## Performance Tips

1. **Enable hierarchical mode** for more uniform chunk sizes
2. **Disable parent emission** (`emit_parent_chunks=False`) for FAISS indexing
3. **Use appropriate chunker**: Don't force tree-sitter on unsupported languages
4. **Set hard_cap_tokens** to match your embedder's max sequence length
5. **Context injection** improves retrieval quality but increases chunk size

---

## Testing

```bash
pytest cpm_builtin/chunking/
pytest cpm_builtin/chunking/test_python_ast.py -v
pytest cpm_builtin/chunking/ -k "hierarchical"
```

---

## See Also

- [cpm_builtin/README.md](../README.md) - Built-in features overview
- [cpm_core/build/README.md](../../cpm_core/build/README.md) - Build system integration
- [cpm_core/packet/README.md](../../cpm_core/packet/README.md) - Packet structure

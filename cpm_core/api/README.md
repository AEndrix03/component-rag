# cpm_core/api - Abstract Interfaces

**Extension points for creating custom commands, builders, and retrievers.**

The `api` package defines the abstract base classes and decorators that enable extensibility in CPM. All custom commands, builders, and retrievers must inherit from these interfaces and use the decorators for automatic registration.

---

## Quick Start

```python
from cpm_core.api import CPMAbstractCommand, cpmcommand

@cpmcommand(name="greet", group="example")
class GreetCommand(CPMAbstractCommand):
    """Greet the user."""

    def configure(self, parser):
        parser.add_argument("--name", default="World")

    def run(self, args):
        print(f"Hello, {args.name}!")
        return 0
```

---

## Components

### CPMAbstractCommand

Base class for all CLI commands.

**Interface:**

```python
class CPMAbstractCommand(Protocol):
    """Abstract base class for CPM commands."""

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """
        Configure the argument parser for this command.

        Args:
            parser: ArgumentParser instance to configure
        """
        ...

    def run(self, args: argparse.Namespace) -> int:
        """
        Execute the command.

        Args:
            args: Parsed command-line arguments

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        ...
```

**Implementation Example:**

```python
from argparse import ArgumentParser, Namespace
from cpm_core.api import CPMAbstractCommand, cpmcommand

@cpmcommand(name="count", group="example")
class CountCommand(CPMAbstractCommand):
    """Count from 1 to N."""

    def configure(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--to",
            type=int,
            default=10,
            help="Count up to this number"
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print verbose output"
        )

    def run(self, args: Namespace) -> int:
        if args.verbose:
            print(f"Counting to {args.to}...")

        for i in range(1, args.to + 1):
            print(i)

        return 0
```

**Usage:**

```bash
cpm example:count --to 5
cpm example:count --to 20 --verbose
```

---

### CPMAbstractBuilder

Base class for packet builders.

**Interface:**

```python
class CPMAbstractBuilder(Protocol):
    """Abstract base class for packet builders."""

    def build(
        self,
        source: str,
        *,
        destination: str | None = None,
    ) -> PacketManifest | None:
        """
        Build a context packet from source.

        Args:
            source: Source directory or file path
            destination: Output directory for packet

        Returns:
            PacketManifest if successful, None otherwise
        """
        ...
```

**Implementation Example:**

```python
from pathlib import Path
from cpm_core.api import CPMAbstractBuilder, cpmbuilder
from cpm_core.packet.models import PacketManifest, EmbeddingSpec

@cpmbuilder(name="simple-builder", group="example")
class SimpleBuilder(CPMAbstractBuilder):
    """A minimal builder that creates basic packets."""

    def build(self, source: str, *, destination: str | None = None) -> PacketManifest | None:
        source_path = Path(source)
        if not source_path.exists():
            print(f"Source {source} does not exist")
            return None

        dest_path = Path(destination) if destination else Path(".") / "output"
        dest_path.mkdir(parents=True, exist_ok=True)

        print(f"Building packet from {source_path} to {dest_path}")

        # Your chunking, embedding, indexing logic here
        # ...

        manifest = PacketManifest(
            schema_version="1.0",
            packet_id=dest_path.name,
            embedding=EmbeddingSpec(
                provider="example",
                model="test-model",
                dim=768,
                dtype="float32",
                normalized=True,
            ),
        )

        return manifest
```

---

### CPMAbstractRetriever

Base class for context retrievers.

**Interface:**

```python
class CPMAbstractRetriever(Protocol):
    """Abstract base class for context retrievers."""

    def retrieve(
        self,
        query: str,
        *,
        k: int = 5,
        **kwargs,
    ) -> list[dict]:
        """
        Retrieve relevant context for a query.

        Args:
            query: Query string
            k: Number of results to return
            **kwargs: Additional retrieval parameters

        Returns:
            List of result dictionaries with 'score', 'text', 'metadata'
        """
        ...
```

**Implementation Example:**

```python
from cpm_core.api import CPMAbstractRetriever

class SimpleRetriever(CPMAbstractRetriever):
    """A basic retriever implementation."""

    def __init__(self, packet_path: str):
        self.packet_path = packet_path

    def retrieve(self, query: str, *, k: int = 5, **kwargs) -> list[dict]:
        # Load FAISS index, embed query, search
        results = []

        # Example result format
        results.append({
            "score": 0.95,
            "text": "Relevant document chunk...",
            "metadata": {
                "path": "docs/intro.md",
                "chunk_id": "intro:0",
            }
        })

        return results[:k]
```

---

## Decorators

### @cpmcommand

Auto-registers a command in the Feature Registry.

**Signature:**

```python
def cpmcommand(
    *,
    name: str,
    group: str = "cpm",
) -> Callable[[type[CPMAbstractCommand]], type[CPMAbstractCommand]]:
    """
    Decorator to register a CPM command.

    Args:
        name: Command name (used in CLI)
        group: Command group (for namespacing)

    Returns:
        Decorated command class
    """
```

**Usage:**

```python
@cpmcommand(name="analyze", group="tools")
class AnalyzeCommand(CPMAbstractCommand):
    """Analyze a codebase."""
    ...
```

**CLI invocation:**

```bash
cpm tools:analyze      # Fully qualified
cpm analyze            # Simple name (if unique)
```

---

### @cpmbuilder

Auto-registers a builder in the Feature Registry.

**Signature:**

```python
def cpmbuilder(
    *,
    name: str,
    group: str = "cpm",
) -> Callable[[type[CPMAbstractBuilder]], type[CPMAbstractBuilder]]:
    """
    Decorator to register a CPM builder.

    Args:
        name: Builder name
        group: Builder group

    Returns:
        Decorated builder class
    """
```

**Usage:**

```python
@cpmbuilder(name="fast-builder", group="builders")
class FastBuilder(CPMAbstractBuilder):
    """High-performance packet builder."""
    ...
```

---

## Complete Example: File Counter Command

```python
"""Example plugin that counts files by extension."""

from argparse import ArgumentParser, Namespace
from pathlib import Path
from collections import Counter

from cpm_core.api import CPMAbstractCommand, cpmcommand
from cpm_core.plugin import PluginContext


@cpmcommand(name="count-files", group="example")
class CountFilesCommand(CPMAbstractCommand):
    """Count files by extension in a directory."""

    def configure(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "directory",
            type=str,
            help="Directory to scan"
        )
        parser.add_argument(
            "--top",
            type=int,
            default=10,
            help="Show top N extensions"
        )

    def run(self, args: Namespace) -> int:
        path = Path(args.directory)

        if not path.exists():
            print(f"Error: {path} does not exist")
            return 1

        if not path.is_dir():
            print(f"Error: {path} is not a directory")
            return 1

        # Count extensions
        extensions = Counter()
        for file in path.rglob("*"):
            if file.is_file():
                ext = file.suffix.lower() or "(no extension)"
                extensions[ext] += 1

        # Display results
        print(f"File count in {path}:\n")
        for ext, count in extensions.most_common(args.top):
            print(f"  {ext:20} {count:>6} files")

        print(f"\nTotal: {sum(extensions.values())} files")

        return 0


def register_plugin(ctx: PluginContext):
    """Plugin entrypoint (called during loading)."""
    # Command auto-registers via @cpmcommand decorator
    ctx.logger.info("Example plugin loaded")
```

**Usage:**

```bash
cpm example:count-files ./src --top 5
```

**Output:**

```
File count in ./src:

  .py                    145 files
  .md                     23 files
  .toml                   12 files
  .json                    8 files
  .yml                     5 files

Total: 193 files
```

---

## Best Practices

### Command Design

1. **Single Responsibility**: Each command should do one thing well
2. **Clear Arguments**: Use descriptive argument names and help text
3. **Exit Codes**: Return 0 on success, non-zero on failure
4. **Error Handling**: Catch exceptions and print user-friendly error messages
5. **Logging**: Use `ctx.logger` for debug/info messages (not print for debug)

### Builder Design

1. **Validation**: Check source and destination before processing
2. **Progress**: Provide feedback during long operations
3. **Cleanup**: Ensure resources are released on error
4. **Manifest**: Always return a valid PacketManifest on success
5. **Incremental**: Support incremental builds when possible

### Naming Conventions

- **Commands**: Verb-based (`build`, `query`, `analyze`)
- **Builders**: Noun-based with `-builder` suffix (`default-builder`, `fast-builder`)
- **Groups**: Lowercase, hyphen-separated (`cpm`, `my-plugin`, `tools`)
- **Names**: Lowercase, hyphen-separated (`count-files`, `greet`)

---

## Testing Custom Commands

```python
from argparse import Namespace
from your_plugin.commands import CountFilesCommand

def test_count_files_command():
    command = CountFilesCommand()
    args = Namespace(directory="./test-data", top=5)

    result = command.run(args)

    assert result == 0
```

---

## See Also

- [cpm_core/plugin/README.md](../plugin/README.md) - Plugin system
- [cpm_core/registry/README.md](../registry/README.md) - Feature Registry
- [cpm_core/README.md](../README.md) - Core documentation

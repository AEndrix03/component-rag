# cpm_core - Foundation Layer

**The core runtime and services powering CPM.**

`cpm_core` provides the foundational layer for Context Packet Manager, including workspace management, service
orchestration, plugin discovery, and feature registration. This is the heart of the CPM system that ties together all
components.

---

## Quick Start

```python
from cpm_core.app import CPMApp

# Bootstrap the CPM application
app = CPMApp(start_dir=".")
status = app.bootstrap()

# Access services
workspace = app.workspace
config = app.config
registry = app.feature_registry
plugin_manager = app.plugin_manager

# Resolve and execute commands
entry = registry.resolve("init")
command = entry.target()
command.run(args)
```

---

## Architecture Overview

```
cpm_core/
├── app.py              # CPMApp orchestrator (entry point)
├── workspace.py        # Workspace, WorkspaceLayout, WorkspaceResolver
├── services.py         # ServiceContainer (lightweight DI)
├── config.py           # ConfigStore (TOML config management)
├── events.py           # EventBus (priority-based pub/sub)
├── plugin/manager.py   # PluginManager (discovery and loading)
├── compat.py           # Legacy command compatibility
├── paths.py            # Platform-aware path utilities
├── api/                # Abstract interfaces for extensibility
│   ├── abc.py          # CPMAbstractCommand, CPMAbstractBuilder, CPMAbstractRetriever
│   └── decorators.py   # @cpmcommand, @cpmbuilder decorators
├── plugin/             # Plugin system implementation
│   ├── manager.py      # Discovery and lifecycle management
│   ├── manifest.py     # Plugin manifest parsing
│   ├── loader.py       # Plugin loading
│   ├── context.py      # PluginContext passed to entrypoints
│   └── errors.py       # Plugin exceptions
├── registry/           # Feature Registry pattern
│   ├── registry.py     # FeatureRegistry (registration and resolution)
│   ├── entry.py        # CPMRegistryEntry
│   ├── client.py       # RegistryClient (remote registry communication)
│   └── errors.py       # Registry exceptions
├── builtins/           # Built-in commands
│   ├── commands.py     # InitCommand, PluginListCommand, PluginDoctorCommand, etc.
│   ├── build.py        # Build command helpers
│   └── pkg.py          # Package management commands
├── build/              # Build system
│   └── builder.py      # DefaultBuilder (chunking + embedding + indexing)
└── packet/             # Packet data structures
    ├── models.py       # DocChunk, PacketManifest, EmbeddingSpec
    ├── faiss_db.py     # FAISS index wrapper
    └── io.py           # Packet I/O utilities
```

---

## Core Components

### CPMApp (`app.py`)

The main application orchestrator that bootstraps all services:

```python
class CPMApp:
    """Entry point that glues the workspace, builtins, registry, and plugins."""

    def __init__(
        self,
        *,
        start_dir: Path | str | None = None,
        user_dirs: UserDirs | None = None,
        logger: logging.Logger | None = None,
        container: ServiceContainer | None = None,
    ):
        # Initializes workspace, config, events, registry, plugins
        ...

    def bootstrap(self) -> CPMAppStatus:
        """
        1. Register core plugin
        2. Register built-in commands/builders
        3. Discover and load plugins
        4. Emit bootstrap event
        5. Ping remote registry (if configured)
        """
        ...
```

**Usage:**

```python
app = CPMApp(start_dir="/path/to/project")
status = app.bootstrap()

print(f"Workspace: {status.workspace.root}")
print(f"Plugins: {', '.join(status.plugins)}")
print(f"Commands: {', '.join(status.commands)}")
print(f"Registry: {status.registry_status}")
```

---

### Workspace (`workspace.py`)

Manages the CPM workspace directory structure:

**Classes:**

- `Workspace`: Represents a CPM workspace with root and config path
- `WorkspaceLayout`: Defines and creates the `.cpm/` directory structure
- `WorkspaceResolver`: Resolves workspace location with fallback to user directories

**Directory Structure:**

```
.cpm/
├── packages/       # Installed packets
├── config/         # Configuration files
├── plugins/        # Workspace plugins
├── cache/          # Query caches
├── state/          # Pins, active versions
├── logs/           # Application logs
└── pins/           # Version pins
```

**Usage:**

```python
from cpm_core.workspace import WorkspaceResolver, WorkspaceLayout

resolver = WorkspaceResolver()
workspace_root = resolver.ensure_workspace(start_dir=Path.cwd())

layout = WorkspaceLayout.from_root(workspace_root, "cpm.toml", "embeddings.yml")
layout.ensure()  # Creates all directories

print(f"Config: {layout.config_file}")
print(f"Plugins: {layout.plugins_dir}")
print(f"Packages: {layout.packages_dir}")
```

---

### ServiceContainer (`services.py`)

Lightweight dependency injection container with lazy singleton initialization:

```python
from cpm_core.services import ServiceContainer

container = ServiceContainer()

# Register service with provider function
container.register("database", lambda c: Database(), singleton=True)

# Resolve service (initializes on first call)
db = container.resolve("database")
```

**Built-in Services:**

- `workspace` - Workspace instance
- `config_store` - ConfigStore instance
- `events` - EventBus instance
- `feature_registry` - FeatureRegistry instance
- `registry_client` - RegistryClient instance
- `plugin_manager` - PluginManager instance

---

### EventBus (`events.py`)

Priority-based publish/subscribe system for plugin lifecycle hooks:

```python
from cpm_core.events import EventBus

bus = EventBus()

# Subscribe to event with priority (higher = earlier)
def on_bootstrap(event_data):
    print(f"Bootstrap: {event_data}")

bus.subscribe("bootstrap", on_bootstrap, priority=10)

# Emit event
bus.emit("bootstrap", {"status": "ready"})
```

**Core Events:**

- `bootstrap` - Application initialization complete
- `plugin.pre_discovery` - Before plugin discovery
- `plugin.post_discovery` - After plugins discovered
- `plugin.pre_plugin_init` - Before loading a plugin
- `plugin.post_plugin_init` - After plugin loaded

---

### ConfigStore (`config.py`)

TOML-based configuration management with layered resolution:

```python
from cpm_core.config import ConfigStore

config = ConfigStore(path=Path(".cpm/config/cpm.toml"))

# Get value with default
embed_url = config.get("embedding.url", default="http://127.0.0.1:8876")

# Set value
config.set("embedding.url", "http://localhost:9000")
config.save()
```

**Configuration Priority:**

1. CLI arguments (highest)
2. Environment variables
3. Workspace config (`.cpm/config/cpm.toml`)
4. User config (`~/.cpm/config.toml`)
5. Defaults (lowest)

---

### PluginManager (`plugin/manager.py`)

Discovers and loads plugins from workspace and user directories:

```python
from cpm_core.plugin_manager import PluginManager

manager = PluginManager(workspace, events, registry=feature_registry)

# Register builtin (core) plugin
manager.register("core")

# Discover and load all plugins
manager.load_plugins()

# List loaded plugins
plugins = manager.list_plugins()  # ("core", "mcp", ...)

# Get plugin details
records = manager.plugin_records()
for record in records:
    print(f"{record.id}: {record.state.value} ({record.source})")
```

**Plugin Lifecycle:**

1. `PENDING` - Discovered but not yet loaded
2. `READY` - Successfully loaded and features registered
3. `FAILED` - Loading failed (error stored in record)

---

## Sub-Packages

### api/ - Abstract Interfaces

Defines the extension points for commands, builders, and retrievers:

- `CPMAbstractCommand` - Base class for CLI commands
- `CPMAbstractBuilder` - Base class for packet builders
- `CPMAbstractRetriever` - Base class for context retrievers
- `@cpmcommand` - Decorator for auto-registration
- `@cpmbuilder` - Decorator for builder registration

[See api/README.md for details](./api/README.md)

### plugin/ - Plugin System

Complete plugin discovery, loading, and lifecycle management:

- `PluginManager` - Discovery and orchestration
- `PluginManifest` - Manifest parsing and validation
- `PluginLoader` - Entrypoint loading
- `PluginContext` - Context passed to plugin entrypoints

[See plugin/README.md for details](./plugin/README.md)

### registry/ - Feature Registry

Manages registration and resolution of commands, builders, and retrievers:

- `FeatureRegistry` - Central registry
- `CPMRegistryEntry` - Feature metadata
- `RegistryClient` - Remote registry communication

[See registry/README.md for details](./registry/README.md)

### builtins/ - Built-in Commands

Core commands that ship with CPM:

- `InitCommand` (`cpm:init`) - Initialize workspace
- `HelpCommand` (`cpm:help`) - Show help
- `ListingCommand` (`cpm:listing`) - List commands
- `PluginListCommand` (`plugin:list`) - List plugins
- `PluginDoctorCommand` (`plugin:doctor`) - Diagnose issues

[See builtins/README.md for details](./builtins/README.md)

### build/ - Build System

Packet building orchestration:

- `DefaultBuilder` - Scans source, chunks, embeds, and indexes
- Incremental building with hash-based caching
- Language-aware chunking integration

[See build/README.md for details](./build/README.md)

### packet/ - Packet Data Structures

Data models and I/O for context packets:

- `DocChunk` - Document chunk with metadata
- `PacketManifest` - Packet metadata (embedding specs, counts, checksums)
- `EmbeddingSpec` - Embedding model configuration
- `FaissFlatIP` - FAISS index wrapper
- I/O utilities (read/write JSONL, vectors, manifests)

[See packet/README.md for details](./packet/README.md)

---

## Programmatic Usage Examples

### Example 1: Custom Command Runner

```python
from cpm_core.app import CPMApp
from cpm_core.registry import FeatureNotFoundError

app = CPMApp(start_dir=".")
app.bootstrap()

try:
    entry = app.feature_registry.resolve("init")
    command = entry.target()

    # Create args namespace
    from argparse import Namespace
    args = Namespace()

    result = command.run(args)
    print(f"Command result: {result}")
except FeatureNotFoundError as e:
    print(f"Command not found: {e}")
```

### Example 2: Event-Driven Extension

```python
from cpm_core.app import CPMApp

app = CPMApp()

# Hook into bootstrap
def on_bootstrap(data):
    print("CPM is ready!")
    print(f"Workspace: {app.workspace.root}")

app.events.subscribe("bootstrap", on_bootstrap, priority=5)
app.bootstrap()
```

### Example 3: Service Access

```python
from cpm_core.app import CPMApp

app = CPMApp()
app.bootstrap()

# Access services via container
workspace = app.container.resolve("workspace")
config = app.container.resolve("config_store")
events = app.container.resolve("events")

print(f"Workspace root: {workspace.root}")
print(f"Config path: {config.path}")
```

---

## Environment Variables

| Variable         | Purpose                 | Default                      |
|------------------|-------------------------|------------------------------|
| `RAG_CPM_DIR`    | Override workspace root | `.cpm`                       |
| `CPM_CONFIG`     | Config file path        | `.cpm/config/cpm.toml`       |
| `CPM_EMBEDDINGS` | Embeddings config path  | `.cpm/config/embeddings.yml` |
| `RAG_EMBED_URL`  | Embedding server URL    | `http://127.0.0.1:8876`      |

---

## Testing

```bash
# Run all tests
pytest

# Run core tests only
pytest tests/test_core.py

# Test with coverage
pytest --cov=cpm_core --cov-report=html
```

---

## See Also

- [cpm_core/api/README.md](./api/README.md) - Abstract interfaces
- [cpm_core/plugin/README.md](./plugin/README.md) - Plugin system
- [cpm_core/registry/README.md](./registry/README.md) - Feature Registry
- [cpm_core/builtins/README.md](./builtins/README.md) - Built-in commands
- [cpm_core/build/README.md](./build/README.md) - Build system
- [cpm_core/packet/README.md](./packet/README.md) - Packet structures

# cpm_core/plugin - Plugin System

**Complete plugin discovery, loading, and lifecycle management for CPM.**

The plugin system enables extending CPM without modifying the core codebase. Plugins can register custom commands,
builders, and retrievers that integrate seamlessly with the CLI.

---

## Quick Start

**Create a plugin:**

```
.cpm/plugins/my-plugin/
├── plugin.toml
└── entrypoint.py
```

**plugin.toml:**

```toml
[plugin]
id = "my-plugin"
name = "My Custom Plugin"
version = "1.0.0"
entrypoint = "entrypoint:register_plugin"
```

**entrypoint.py:**

```python
from cpm_core.api import cpmcommand, CPMAbstractCommand
from cpm_core.plugin import PluginContext

@cpmcommand(name="hello", group="my-plugin")
class HelloCommand(CPMAbstractCommand):
    def configure(self, parser):
        pass

    def run(self, args):
        print("Hello from my plugin!")
        return 0

def register_plugin(ctx: PluginContext):
    ctx.logger.info("Plugin loaded!")
```

**Test:**

```bash
cpm plugin:list
cpm my-plugin:hello
```

---

## Architecture

### Components

| Component        | Purpose                                                             |
|------------------|---------------------------------------------------------------------|
| `PluginManager`  | Orchestrates discovery, loading, and lifecycle                      |
| `PluginManifest` | Parses and validates `plugin.toml`                                  |
| `PluginLoader`   | Loads Python entrypoint and calls register function                 |
| `PluginContext`  | Context passed to entrypoints (workspace, registry, events, logger) |
| `PluginRecord`   | Tracks plugin state (PENDING → READY/FAILED)                        |

### Plugin Lifecycle

```
┌─────────────┐
│   PENDING   │  Plugin discovered, not yet loaded
└──────┬──────┘
       │
       ├─ load entrypoint
       ├─ call register_plugin(ctx)
       ├─ register features in FeatureRegistry
       │
       ├─ Success ──→ ┌───────┐
       │              │ READY │  Features available
       │              └───────┘
       │
       └─ Failure ──→ ┌────────┐
                      │ FAILED │  Error recorded
                      └────────┘
```

### Discovery Flow

1. **Pre-Discovery Event**: `plugin.pre_discovery` emitted
2. **Scan Directories**:
    - Workspace plugins: `.cpm/plugins/`
    - User plugins: `~/.cpm/plugins/` (or `%APPDATA%/cpm/plugins` on Windows)
3. **Find Manifests**: Look for `plugin.toml` in subdirectories
4. **Parse Manifests**: Validate structure and extract metadata
5. **Post-Discovery Event**: `plugin.post_discovery` emitted with plugin list
6. **Load Plugins**: For each plugin, emit `pre_plugin_init` → load → emit `post_plugin_init`

---

## PluginManager

**Manages plugin discovery and loading.**

### API

```python
class PluginManager:
    def __init__(
        self,
        workspace: Workspace,
        events: EventBus,
        *,
        user_dirs: UserDirs | None = None,
        registry: FeatureRegistry | None = None,
    ):
        """
        Initialize plugin manager.

        Args:
            workspace: Current workspace
            events: Event bus for lifecycle hooks
            user_dirs: User directory configuration
            registry: Feature registry for command registration
        """

    def register(self, name: str, *, state: PluginState | None = PluginState.READY):
        """Register a plugin identifier (used for builtins)."""

    def load_plugins(self):
        """Discover and load all plugins from workspace and user paths."""

    def list_plugins(self) -> tuple[str, ...]:
        """Return list of registered plugin IDs."""

    def plugin_records(self) -> tuple[PluginRecord, ...]:
        """Return detailed records for all plugins."""
```

### Usage Example

```python
from cpm_core.plugin_manager import PluginManager
from cpm_core.workspace import Workspace
from cpm_core.events import EventBus
from cpm_core.registry import FeatureRegistry

workspace = Workspace(root=Path(".cpm"), config_path=Path(".cpm/config/cpm.toml"))
events = EventBus()
registry = FeatureRegistry()

manager = PluginManager(workspace, events, registry=registry)

# Register core plugin
manager.register("core")

# Load all plugins
manager.load_plugins()

# List plugins
for plugin_id in manager.list_plugins():
    print(f"Loaded: {plugin_id}")

# Get detailed status
for record in manager.plugin_records():
    print(f"{record.id}: {record.state.value}")
    if record.error:
        print(f"  Error: {record.error}")
```

---

## PluginManifest

**Parses and validates `plugin.toml` manifests.**

### Schema

```toml
[plugin]
id = "my-plugin"                     # Required: Plugin identifier
name = "My Plugin"                   # Required: Human-readable name
version = "1.0.0"                    # Required: Semantic version
description = "Does something cool"  # Optional: Brief description
entrypoint = "entrypoint:register_plugin"  # Required: Python module:function

[plugin.metadata]
author = "Your Name"                 # Optional
license = "MIT"                      # Optional
homepage = "https://example.com"     # Optional
```

### API

```python
@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    entrypoint: str
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "PluginManifest":
        """Load and validate manifest from plugin.toml."""
```

### Usage

```python
from pathlib import Path
from cpm_core.plugin.manifest import PluginManifest

manifest = PluginManifest.load(Path(".cpm/plugins/my-plugin/plugin.toml"))

print(f"ID: {manifest.id}")
print(f"Name: {manifest.name}")
print(f"Version: {manifest.version}")
print(f"Entrypoint: {manifest.entrypoint}")
```

---

## PluginLoader

**Loads plugin entrypoints and executes registration.**

### API

```python
class PluginLoader:
    def __init__(self, manifest: PluginManifest, context: PluginContext):
        """
        Initialize loader.

        Args:
            manifest: Plugin manifest
            context: Context to pass to entrypoint
        """

    def load(self) -> list[CPMRegistryEntry]:
        """
        Load plugin and return registered features.

        Raises:
            PluginLoadError: If entrypoint fails to load or execute
        """
```

### Loading Process

1. **Parse Entrypoint**: Split `module:function` from manifest
2. **Add Plugin Root to sys.path**: Enable import of plugin modules
3. **Import Module**: `importlib.import_module(module_name)`
4. **Get Function**: `getattr(module, function_name)`
5. **Call Entrypoint**: `entrypoint_function(context)`
6. **Return Features**: Features registered via decorators are captured

---

## PluginContext

**Context passed to plugin entrypoints.**

### API

```python
@dataclass(frozen=True)
class PluginContext:
    manifest: PluginManifest         # Plugin metadata
    plugin_root: Path                # Plugin directory path
    workspace_root: Path             # Workspace root path
    registry: FeatureRegistry        # For registering features
    events: EventBus                 # For subscribing to events
    logger: logging.Logger           # Plugin-specific logger
```

### Usage in Entrypoint

```python
from cpm_core.plugin import PluginContext
from cpm_core.api import cpmcommand, CPMAbstractCommand

@cpmcommand(name="status", group="my-plugin")
class StatusCommand(CPMAbstractCommand):
    def configure(self, parser):
        pass

    def run(self, args):
        print("Status: OK")
        return 0

def register_plugin(ctx: PluginContext):
    # Access plugin metadata
    ctx.logger.info(f"Loading {ctx.manifest.name} v{ctx.manifest.version}")

    # Subscribe to events
    def on_bootstrap(data):
        ctx.logger.info("CPM bootstrapped!")

    ctx.events.subscribe("bootstrap", on_bootstrap, priority=5)

    # Load plugin-specific config
    config_file = ctx.plugin_root / "config.toml"
    if config_file.exists():
        ctx.logger.info(f"Loaded config from {config_file}")

    # Features auto-register via @cpmcommand decorator
```

---

## Plugin Events

### Available Events

| Event                     | When                    | Payload                                                  |
|---------------------------|-------------------------|----------------------------------------------------------|
| `plugin.pre_discovery`    | Before plugin discovery | `{"workspace_plugins": str, "user_plugins": str}`        |
| `plugin.post_discovery`   | After discovery         | `{"plugins": list[str]}`                                 |
| `plugin.pre_plugin_init`  | Before loading a plugin | `{"plugin_id": str, "source": str}`                      |
| `plugin.post_plugin_init` | After plugin loaded     | `{"plugin_id": str, "state": str, "error": str \| None}` |

### Subscribing to Events

```python
def register_plugin(ctx: PluginContext):
    def on_plugin_loaded(data):
        if data["state"] == "ready":
            ctx.logger.info(f"Plugin {data['plugin_id']} loaded successfully")

    ctx.events.subscribe("plugin.post_plugin_init", on_plugin_loaded)
```

---

## Error Handling

### Plugin Exceptions

```python
from cpm_core.plugin.errors import PluginLoadError, PluginManifestError

# Raised when manifest is invalid
raise PluginManifestError("Missing required field: entrypoint")

# Raised when entrypoint fails to load
raise PluginLoadError("Module 'foo' not found")
```

### Handling Failed Plugins

```python
for record in manager.plugin_records():
    if record.state == PluginState.FAILED:
        print(f"Plugin {record.id} failed to load:")
        print(f"  Error: {record.error}")
        print(f"  Source: {record.source}")
```

---

## Complete Plugin Example

**Directory structure:**

```
.cpm/plugins/devtools/
├── plugin.toml
├── entrypoint.py
└── helpers.py
```

**plugin.toml:**

```toml
[plugin]
id = "devtools"
name = "Developer Tools"
version = "1.0.0"
description = "Useful commands for developers"
entrypoint = "entrypoint:register_plugin"

[plugin.metadata]
author = "Dev Team"
license = "MIT"
```

**helpers.py:**

```python
"""Shared utilities for devtools plugin."""

def count_lines(file_path):
    with open(file_path) as f:
        return sum(1 for _ in f)
```

**entrypoint.py:**

```python
"""Devtools plugin entrypoint."""

from pathlib import Path
from argparse import ArgumentParser, Namespace

from cpm_core.api import CPMAbstractCommand, cpmcommand
from cpm_core.plugin import PluginContext

from .helpers import count_lines


@cpmcommand(name="loc", group="devtools")
class LineCountCommand(CPMAbstractCommand):
    """Count lines of code in a file or directory."""

    def configure(self, parser: ArgumentParser):
        parser.add_argument("path", help="File or directory to analyze")
        parser.add_argument("--ext", default=".py", help="File extension to count")

    def run(self, args: Namespace) -> int:
        path = Path(args.path)

        if not path.exists():
            print(f"Error: {path} does not exist")
            return 1

        if path.is_file():
            lines = count_lines(path)
            print(f"{path}: {lines} lines")
            return 0

        # Directory: count all matching files
        total = 0
        for file in path.rglob(f"*{args.ext}"):
            if file.is_file():
                lines = count_lines(file)
                total += lines
                print(f"{file.relative_to(path)}: {lines} lines")

        print(f"\nTotal: {total} lines")
        return 0


def register_plugin(ctx: PluginContext):
    ctx.logger.info(f"Loaded {ctx.manifest.name} v{ctx.manifest.version}")

    # Subscribe to bootstrap event
    def on_bootstrap(data):
        ctx.logger.debug("Devtools plugin ready")

    ctx.events.subscribe("bootstrap", on_bootstrap)
```

**Usage:**

```bash
cpm devtools:loc ./src
cpm devtools:loc ./main.py
cpm devtools:loc ./src --ext .js
```

---

## Best Practices

1. **Unique IDs**: Use descriptive, unique plugin IDs
2. **Versioning**: Follow semantic versioning
3. **Error Handling**: Catch and log exceptions gracefully
4. **Documentation**: Include docstrings for all commands
5. **Testing**: Test plugins independently before installation
6. **Dependencies**: Document any external dependencies in plugin docs
7. **Logging**: Use `ctx.logger` for debug/info messages, not `print`

---

## Troubleshooting

**Plugin not discovered:**

- Check that `plugin.toml` exists in `.cpm/plugins/<plugin-id>/`
- Verify plugin ID matches directory name
- Run `cpm plugin:doctor` to diagnose

**Plugin fails to load:**

- Check `entrypoint` format: `module:function`
- Verify entrypoint function signature: `def register_plugin(ctx: PluginContext)`
- Check logs for import errors

**Feature collision:**

- Use unique qualified names (`group:name`)
- Check for name conflicts with `cpm listing`

---

## See Also

- [cpm_core/api/README.md](../api/README.md) - Abstract interfaces
- [cpm_core/registry/README.md](../registry/README.md) - Feature Registry
- [cpm_plugins/README.md](../../cpm_plugins/README.md) - Official plugins

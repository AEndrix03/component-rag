# cpm_plugins - Official CPM Plugins

**Extensibility modules for CPM.**

This directory contains official plugins that extend CPM functionality. Plugins are discovered via `plugin.toml`
manifests and registered through the CPM plugin system.

---

## Available Plugins

### MCP Plugin (`cpm_plugins/mcp/`)

Model Context Protocol (MCP) integration for Claude Desktop.

- **Status**: Official
- **Purpose**: Expose CPM packets as MCP tools for Claude Desktop
- **Tools**: `lookup` (list packets), `query` (semantic search)
- **Transport**: stdio (for Claude Desktop integration)

[See mcp/README.md for details](./mcp/README.md)

---

## Plugin Structure

Each plugin follows this structure:

```
cpm_plugins/my_plugin/
├── plugin.toml                    # Plugin manifest
├── cpm_my_plugin/                 # Plugin package
│   ├── __init__.py
│   ├── entrypoint.py              # Entrypoint class
│   ├── features.py                # Commands/builders/retrievers
│   └── ...                        # Additional modules
└── README.md                      # Plugin documentation
```

---

## Plugin Manifest (`plugin.toml`)

Each plugin declares its metadata in `plugin.toml`:

```toml
[plugin]
id = "my-plugin"
name = "My CPM Plugin"
version = "0.1.0"
group = "my-plugin"
entrypoint = "cpm_my_plugin.entrypoint:MyEntrypoint"
requires_cpm = ">=0.1.0"
```

**Fields:**

| Field          | Type   | Required | Description                                     |
|----------------|--------|----------|-------------------------------------------------|
| `id`           | string | Yes      | Unique plugin identifier (kebab-case)           |
| `name`         | string | Yes      | Human-readable plugin name                      |
| `version`      | string | Yes      | Plugin version (semantic versioning)            |
| `group`        | string | No       | Default group for features (default: plugin id) |
| `entrypoint`   | string | Yes      | Python import path to entrypoint class          |
| `requires_cpm` | string | No       | CPM version requirement                         |

---

## Entrypoint Pattern

All plugins must provide an entrypoint class with an `init` method:

```python
# cpm_my_plugin/entrypoint.py

from cpm_core.plugin import PluginContext

class MyEntrypoint:
    """Plugin entrypoint."""

    def init(self, ctx: PluginContext) -> None:
        """Initialize the plugin."""
        self.context = ctx
        ctx.logger.info(f"Initialized {ctx.plugin_id}")

        # Features auto-register via decorators
        from . import features  # noqa
```

**PluginContext API:**

```python
@dataclass
class PluginContext:
    plugin_id: str              # Plugin ID
    plugin_dir: Path            # Plugin directory
    workspace: Workspace        # CPM workspace
    config: ConfigStore         # Configuration
    events: EventBus            # Event bus
    registry: FeatureRegistry   # Feature registry
    logger: logging.Logger      # Plugin logger
    container: ServiceContainer # Service container
```

---

## Registering Features

Plugins register commands, builders, and retrievers using decorators:

### Commands

```python
# cpm_my_plugin/features.py

from argparse import ArgumentParser, Namespace
from cpm_core.api import CPMAbstractCommand, cpmcommand

@cpmcommand(name="hello", group="my-plugin")
class HelloCommand(CPMAbstractCommand):
    """Say hello."""

    def configure(self, parser: ArgumentParser) -> None:
        parser.add_argument("--name", default="World")

    def run(self, args: Namespace) -> int:
        print(f"Hello, {args.name}!")
        return 0
```

**Usage:**

```bash
cpm my-plugin:hello --name Alice
cpm hello  # If name is unique
```

### Builders

```python
from cpm_core.api import CPMAbstractBuilder, cpmbuilder
from cpm_core.packet.models import PacketManifest

@cpmbuilder(name="custom-builder", group="my-plugin")
class CustomBuilder(CPMAbstractBuilder):
    """Custom packet builder."""

    def build(self, source: str, *, destination: str | None = None) -> PacketManifest | None:
        # Build logic here
        return manifest
```

### Retrievers

```python
from cpm_core.api import CPMAbstractRetriever

class CustomRetriever(CPMAbstractRetriever):
    """Custom retriever implementation."""

    def retrieve(self, query: str, *, k: int = 5, **kwargs) -> list[dict]:
        # Retrieval logic here
        return results
```

---

## Plugin Discovery

Plugins are discovered from:

1. **Workspace plugins**: `.cpm/plugins/`
2. **User plugins**: `~/.cpm/plugins/`

The plugin manager scans these directories for `plugin.toml` files.

---

## Plugin Lifecycle

1. **Discovery**: Plugin manager finds `plugin.toml` files
2. **Validation**: Manifest is parsed and validated
3. **Loading**: Entrypoint is imported
4. **Initialization**: `entrypoint.init(ctx)` is called
5. **Registration**: Features are registered via decorators
6. **Ready**: Plugin is marked as ready

**Lifecycle Events:**

- `plugin.pre_discovery`: Before plugin discovery
- `plugin.post_discovery`: After plugins discovered
- `plugin.pre_plugin_init`: Before loading a plugin
- `plugin.post_plugin_init`: After plugin loaded

---

## Example: Simple Plugin

### Directory Structure

```
cpm_plugins/greeter/
├── plugin.toml
├── cpm_greeter/
│   ├── __init__.py
│   ├── entrypoint.py
│   └── features.py
└── README.md
```

### plugin.toml

```toml
[plugin]
id = "greeter"
name = "Greeter Plugin"
version = "0.1.0"
group = "greeter"
entrypoint = "cpm_greeter.entrypoint:GreeterEntrypoint"
requires_cpm = ">=0.1.0"
```

### entrypoint.py

```python
"""Greeter plugin entrypoint."""

from cpm_core.plugin import PluginContext

class GreeterEntrypoint:
    """Initialize the greeter plugin."""

    def init(self, ctx: PluginContext) -> None:
        self.context = ctx
        ctx.logger.info("Greeter plugin initialized")

        # Import features to trigger auto-registration
        from . import features  # noqa
```

### features.py

```python
"""Greeter commands."""

from argparse import ArgumentParser, Namespace
from cpm_core.api import CPMAbstractCommand, cpmcommand

@cpmcommand(name="greet", group="greeter")
class GreetCommand(CPMAbstractCommand):
    """Greet someone."""

    def configure(self, parser: ArgumentParser) -> None:
        parser.add_argument("name", help="Name to greet")
        parser.add_argument("--formal", action="store_true")

    def run(self, args: Namespace) -> int:
        if args.formal:
            print(f"Good day, {args.name}.")
        else:
            print(f"Hey, {args.name}!")
        return 0
```

### Usage

```bash
cpm greeter:greet Alice
# Hey, Alice!

cpm greeter:greet Bob --formal
# Good day, Bob.
```

---

## Plugin Development Guide

### 1. Create Plugin Directory

```bash
mkdir -p cpm_plugins/my_plugin/cpm_my_plugin
```

### 2. Create Manifest

```toml
# cpm_plugins/my_plugin/plugin.toml
[plugin]
id = "my-plugin"
name = "My Plugin"
version = "0.1.0"
group = "my-plugin"
entrypoint = "cpm_my_plugin.entrypoint:MyEntrypoint"
```

### 3. Create Entrypoint

```python
# cpm_plugins/my_plugin/cpm_my_plugin/entrypoint.py

class MyEntrypoint:
    def init(self, ctx):
        self.context = ctx
        from . import features  # noqa
```

### 4. Add Features

```python
# cpm_plugins/my_plugin/cpm_my_plugin/features.py

from cpm_core.api import CPMAbstractCommand, cpmcommand

@cpmcommand(name="my-command", group="my-plugin")
class MyCommand(CPMAbstractCommand):
    def configure(self, parser):
        parser.add_argument("--arg")

    def run(self, args):
        print(f"Running with {args.arg}")
        return 0
```

### 5. Test Plugin

```bash
# From repository root
cpm plugin:list
cpm my-plugin:my-command --arg test
```

### 6. Write Tests

```python
# tests/test_my_plugin.py

from cpm_core.app import CPMApp

def test_my_plugin_loads():
    app = CPMApp(start_dir=".")
    status = app.bootstrap()

    assert "my-plugin" in status.plugins

    entry = app.feature_registry.resolve("my-command")
    assert entry is not None
```

---

## Plugin Best Practices

### 1. Use Descriptive IDs

```toml
# Good
id = "mcp-integration"

# Bad
id = "plugin1"
```

### 2. Provide Clear Documentation

```markdown
# My Plugin

Brief description of what the plugin does.

## Features
- Feature 1
- Feature 2

## Usage
...
```

### 3. Handle Errors Gracefully

```python
def run(self, args):
    try:
        # Plugin logic
        return 0
    except ValueError as e:
        print(f"Error: {e}")
        return 1
```

### 4. Use Logging

```python
def init(self, ctx):
    self.context = ctx
    ctx.logger.info("Plugin initialized")
    ctx.logger.debug("Debug information")
```

### 5. Version Compatibility

```toml
requires_cpm = ">=0.1.0"  # Minimum CPM version
```

### 6. Namespace Features

```python
@cpmcommand(name="serve", group="mcp")  # mcp:serve
```

---

## Plugin Installation

### Workspace Plugins

Place in `.cpm/plugins/`:

```
.cpm/plugins/
└── my-plugin/
    ├── plugin.toml
    └── cpm_my_plugin/
        └── ...
```

### User Plugins

Place in `~/.cpm/plugins/`:

```
~/.cpm/plugins/
└── my-plugin/
    ├── plugin.toml
    └── cpm_my_plugin/
        └── ...
```

---

## Debugging Plugins

### List Loaded Plugins

```bash
cpm plugin:list
```

### Check Plugin Status

```bash
cpm plugin:doctor
```

**Output:**

```
Plugin Status:
  core: READY
  mcp: READY
  my-plugin: FAILED (ImportError: No module named 'cpm_my_plugin')
```

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## See Also

- [cpm_plugins/mcp/README.md](./mcp/README.md) - MCP plugin details
- [cpm_core/plugin/README.md](../cpm_core/plugin/README.md) - Plugin system
- [cpm_core/api/README.md](../cpm_core/api/README.md) - API abstractions
- [cpm_core/registry/README.md](../cpm_core/registry/README.md) - Feature registry

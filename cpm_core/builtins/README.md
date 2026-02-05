# cpm_core/builtins - Built-in Commands

**Core commands that ship with CPM.**

This package contains the essential commands registered before plugins are loaded. These commands provide workspace
initialization, plugin management, and system diagnostics.

---

## Commands

### InitCommand (`cpm:init`)

Initialize a new CPM workspace.

**Usage:**

```bash
cpm init
```

**What it does:**

- Creates `.cpm/` directory structure
- Generates default `config/cpm.toml`
- Creates `config/embeddings.yml` template
- Sets up workspace directories (packages, plugins, cache, logs, state)

**Implementation:** `commands.py`

---

### HelpCommand (`cpm:help`)

Display available commands with descriptions.

**Usage:**

```bash
cpm help
cpm help --long    # Show detailed descriptions
```

**Output:**

```
Usage: cpm <command> [args...]

Core commands:
  init                           Initialize CPM workspace
  help                           Show this help message
  listing                        List all commands
  ...

Plugin commands:
  mcp:serve                      Start MCP server
  ...

Use group:name to disambiguate commands when needed.
```

**Implementation:** `commands.py`

---

### ListingCommand (`cpm:listing`)

List all registered commands in machine-readable format.

**Usage:**

```bash
cpm listing                # Plain text output
cpm listing --format json  # JSON output
```

**Output (text):**

```
init
help
listing
plugin:list
plugin:doctor
mcp:serve
```

**Output (JSON):**

```json
[
  "init",
  "help",
  "listing",
  "plugin:list",
  "plugin:doctor",
  "mcp:serve"
]
```

**Implementation:** `commands.py`

---

### PluginListCommand (`plugin:list`)

List loaded plugins.

**Usage:**

```bash
cpm plugin:list
cpm plugin:list --include-builtin  # Include "core" plugin
```

**Output:**

```
core
mcp
devtools
```

**Implementation:** `commands.py`

---

### PluginDoctorCommand (`plugin:doctor`)

Diagnose workspace and plugin issues.

**Usage:**

```bash
cpm plugin:doctor
cpm doctor  # Alias
```

**What it checks:**

- Workspace layout validity
- Configuration file existence and syntax
- Embeddings configuration
- Plugin discovery and status
- Legacy command aliases
- Registry connectivity

**Sample Output:**

```
CPM Doctor Report
=================

Workspace Layout: ✓ OK
  Root: C:\Users\user\project\.cpm
  Config: C:\Users\user\project\.cpm\config\cpm.toml
  Embeddings: C:\Users\user\project\.cpm\config\embeddings.yml

Plugins: ✓ 3 loaded
  - core (builtin, READY)
  - mcp (plugin, READY)
  - devtools (plugin, READY)

Configuration: ✓ Valid
  Embedding URL: http://127.0.0.1:8876

Registry: ✓ Connected
  URL: http://localhost:8786

Legacy Commands: Available
  lookup   → pkg:list
  use      → pkg:use
  prune    → pkg:prune
  mcp serve → serve
```

**Implementation:** `commands.py`

---

## Helper Modules

### build.py

Build command helpers and utilities (used by `cpm_builtin/build.py`).

**Functions:**

- Configuration parsing
- Source scanning
- Build orchestration helpers

---

### pkg.py

Package management command implementations.

**Commands:**

- `pkg:list` - List installed packages
- `pkg:use` - Pin package version
- `pkg:prune` - Remove old versions

**Usage:**

```bash
cpm pkg:list
cpm pkg:use my-package@1.2.0
cpm pkg:prune my-package --keep 2
```

---

## Registration

Built-in commands are registered during `CPMApp.bootstrap()`:

```python
# cpm_core/app.py
def bootstrap(self):
    self.plugin_manager.register("core")
    self._register_builtins()  # Registers all builtin commands
    self.plugin_manager.load_plugins()
    ...

# cpm_core/builtins/__init__.py
def register_builtin_commands(registry: FeatureRegistry):
    """Register all built-in commands."""
    registry.register(CPMRegistryEntry(
        name="init",
        group="cpm",
        target=InitCommand,
        origin="builtin",
    ))
    registry.register(CPMRegistryEntry(
        name="help",
        group="cpm",
        target=HelpCommand,
        origin="builtin",
    ))
    # ... more commands
```

---

## Command Groups

| Group    | Commands            | Purpose                           |
|----------|---------------------|-----------------------------------|
| `cpm`    | init, help, listing | Core workspace operations         |
| `plugin` | list, doctor        | Plugin management and diagnostics |
| `pkg`    | list, use, prune    | Package management                |

---

## Testing Built-in Commands

```python
from argparse import Namespace
from cpm_core.builtins.commands import InitCommand

def test_init_command():
    command = InitCommand()
    args = Namespace()

    result = command.run(args)

    assert result == 0
    assert Path(".cpm").exists()
    assert Path(".cpm/config").exists()
```

---

## See Also

- [cpm_core/api/README.md](../api/README.md) - Command interfaces
- [cpm_core/registry/README.md](../registry/README.md) - Feature Registry
- [cpm_builtin/README.md](../../cpm_builtin/README.md) - Built-in features

# cpm_core/registry - Feature Registry

**Central registry for commands, builders, and retrievers with intelligent name resolution.**

The Feature Registry enables automatic command discovery, handles name collisions, and provides disambiguation for features registered by plugins and builtins.

---

## Quick Start

```python
from cpm_core.registry import FeatureRegistry, CPMRegistryEntry

registry = FeatureRegistry()

# Register a command
entry = CPMRegistryEntry(
    name="build",
    group="cpm",
    target=BuildCommand,
    origin="builtin",
)
registry.register(entry)

# Resolve by simple name
entry = registry.resolve("build")

# Resolve by qualified name
entry = registry.resolve("cpm:build")
```

---

## Components

### FeatureRegistry

**Central registry tracking all features.**

**API:**

```python
class FeatureRegistry:
    def register(self, entry: CPMRegistryEntry) -> None:
        """
        Register a feature.

        Raises:
            FeatureCollisionError: If qualified name already exists
        """

    def resolve(self, name_or_qualified: str) -> CPMRegistryEntry:
        """
        Resolve a feature by simple or qualified name.

        Args:
            name_or_qualified: "build" or "cpm:build"

        Returns:
            CPMRegistryEntry

        Raises:
            FeatureNotFoundError: Feature not registered
            AmbiguousFeatureError: Multiple features with same simple name
        """

    def display_names(self) -> tuple[str, ...]:
        """
        Return user-facing names.

        Returns simple names when unique, qualified names when ambiguous.
        """

    def entries(self) -> tuple[CPMRegistryEntry, ...]:
        """Return all registered entries."""
```

### Name Resolution Strategy

1. **Check for colon** in input → qualified name lookup
2. **No colon** → simple name lookup:
   - If unique → return entry
   - If multiple → raise `AmbiguousFeatureError`
   - If none → raise `FeatureNotFoundError`

**Examples:**

```python
# Single "build" registered
registry.resolve("build")        # ✓ Returns cpm:build

# Two "build" commands registered (cpm:build, plugin:build)
registry.resolve("build")        # ✗ AmbiguousFeatureError
registry.resolve("cpm:build")    # ✓ Returns cpm:build
registry.resolve("plugin:build") # ✓ Returns plugin:build
```

---

### CPMRegistryEntry

**Metadata for a registered feature.**

```python
@dataclass(frozen=True)
class CPMRegistryEntry:
    name: str                       # Simple name ("build")
    group: str                      # Group ("cpm", "plugin")
    target: type                    # Command/Builder class
    origin: str = "unknown"         # "builtin" or "plugin"
    description: str | None = None  # Optional description

    @property
    def qualified_name(self) -> str:
        """Return group:name ("cpm:build")."""
        return f"{self.group}:{self.name}"
```

**Usage:**

```python
from cpm_core.registry import CPMRegistryEntry
from cpm_core.api import CPMAbstractCommand

entry = CPMRegistryEntry(
    name="greet",
    group="example",
    target=GreetCommand,
    origin="plugin",
    description="Greet the user",
)

print(entry.qualified_name)  # "example:greet"
print(entry.name)             # "greet"
print(entry.group)            # "example"
```

---

## Usage Examples

### Example 1: Basic Registration

```python
from cpm_core.registry import FeatureRegistry, CPMRegistryEntry

registry = FeatureRegistry()

# Register commands
registry.register(CPMRegistryEntry(
    name="init",
    group="cpm",
    target=InitCommand,
    origin="builtin",
))

registry.register(CPMRegistryEntry(
    name="hello",
    group="example",
    target=HelloCommand,
    origin="plugin",
))

# List all commands
for entry in registry.entries():
    print(entry.qualified_name)
# Output:
# cpm:init
# example:hello
```

### Example 2: Name Collision Handling

```python
from cpm_core.registry import AmbiguousFeatureError, FeatureNotFoundError

registry = FeatureRegistry()

# Register two "build" commands
registry.register(CPMRegistryEntry(name="build", group="cpm", target=CoreBuild, origin="builtin"))
registry.register(CPMRegistryEntry(name="build", group="plugin", target=PluginBuild, origin="plugin"))

# Simple name is ambiguous
try:
    registry.resolve("build")
except AmbiguousFeatureError as e:
    print(f"Ambiguous: {e.candidates}")  # ["cpm:build", "plugin:build"]

# Use qualified names
core_entry = registry.resolve("cpm:build")
plugin_entry = registry.resolve("plugin:build")
```

### Example 3: Display Names

```python
registry = FeatureRegistry()

# Register unique "init" and ambiguous "build"
registry.register(CPMRegistryEntry(name="init", group="cpm", target=InitCommand, origin="builtin"))
registry.register(CPMRegistryEntry(name="build", group="cpm", target=CoreBuild, origin="builtin"))
registry.register(CPMRegistryEntry(name="build", group="plugin", target=PluginBuild, origin="plugin"))

names = registry.display_names()
print(names)
# ("cpm:build", "init", "plugin:build")
# Note: "init" is simple (unique), "build" shows qualified (ambiguous)
```

---

## Error Handling

### FeatureCollisionError

Raised when attempting to register a feature with an already-registered qualified name.

```python
from cpm_core.registry import FeatureCollisionError

try:
    registry.register(CPMRegistryEntry(name="init", group="cpm", target=Cmd1, origin="builtin"))
    registry.register(CPMRegistryEntry(name="init", group="cpm", target=Cmd2, origin="builtin"))
except FeatureCollisionError as e:
    print(f"Collision: {e}")
```

### AmbiguousFeatureError

Raised when resolving a simple name that has multiple registrations.

```python
from cpm_core.registry import AmbiguousFeatureError

try:
    entry = registry.resolve("build")  # Multiple "build" commands
except AmbiguousFeatureError as e:
    print(f"Did you mean one of: {', '.join(e.candidates)}?")
```

### FeatureNotFoundError

Raised when resolving a name that doesn't exist.

```python
from cpm_core.registry import FeatureNotFoundError

try:
    entry = registry.resolve("nonexistent")
except FeatureNotFoundError as e:
    print(f"Not found: {e}")
```

---

## Integration with CLI

The CLI uses the Feature Registry to resolve commands:

```python
# cpm_cli/main.py
from cpm_core.app import CPMApp

app = CPMApp()
app.bootstrap()

try:
    entry = app.feature_registry.resolve("init")
    command = entry.target()
    result = command.run(args)
except FeatureNotFoundError:
    print("Command not found")
except AmbiguousFeatureError as e:
    print(f"Ambiguous. Use: {', '.join(e.candidates)}")
```

---

## RegistryClient

**Client for communicating with remote CPM registries.**

**API:**

```python
class RegistryClient:
    def ping(self) -> str:
        """Check registry connectivity."""

    @property
    def status(self) -> str:
        """Get registry status string."""
```

This client is used for package publishing/installation workflows (not feature registration).

---

## Best Practices

1. **Unique Groups**: Use descriptive group names for your plugins
2. **Qualified Names**: Always provide both `name` and `group` when registering
3. **Handle Collisions**: Expect and handle `AmbiguousFeatureError` in CLI code
4. **Document Aliases**: If providing common shortcuts, document them clearly
5. **Origin Tracking**: Set `origin` to "builtin" or "plugin" for debugging

---

## See Also

- [cpm_core/api/README.md](../api/README.md) - Abstract interfaces
- [cpm_core/plugin/README.md](../plugin/README.md) - Plugin system
- [cpm_cli/README.md](../../cpm_cli/README.md) - CLI routing

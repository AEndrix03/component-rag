# cpm_cli - CLI Routing Layer

**Command-line interface routing and resolution for CPM.**

`cpm_cli` provides the CLI entry point that resolves command tokens against the Feature Registry and dispatches to the
appropriate handlers, including legacy command support.

---

## Quick Start

```bash
# Core commands (routed via FeatureRegistry)
cpm init
cpm help
cpm plugin:list

# Embed commands (delegated to cpm_cli/cli.py)
cpm embed add --name local --url http://127.0.0.1:8876

# Legacy commands (backward compatibility)
cpm lookup     # → pkg:list
cpm lookup     # → cpm pkg list
```

---

## Architecture

```
User Input: "cpm plugin:list --verbose"
       │
       ├─ Parse tokens: ["plugin:list", "--verbose"]
       │
       ├─ Check special cases:
       │   ├─ "embed" → delegate to cpm_cli/cli.py
       │   └─ compatibility aliases → map to modular commands
       │
       ├─ Bootstrap CPMApp
       │   ├─ Load workspace
       │   ├─ Register builtins
       │   └─ Load plugins
       │
       ├─ Extract command spec
       │   ├─ Try qualified: "plugin:list"
       │   └─ Try compound: "plugin" + "list"
       │
       ├─ Resolve via FeatureRegistry
       │   └─ entry = registry.resolve("plugin:list")
       │
       ├─ Configure ArgumentParser
       │   └─ entry.target.configure(parser)
       │
       ├─ Parse arguments
       │   └─ args = parser.parse_args(["--verbose"])
       │
       ├─ Instantiate command
       │   └─ command = entry.target()
       │
       └─ Execute
           └─ result = command.run(args)
```

---

## Command Resolution

### Token Extraction

The CLI extracts command specifications from input tokens:

**Pattern 1: Qualified name**

```bash
cpm plugin:list --verbose
# Tokens: ["plugin:list", "--verbose"]
# Spec: "plugin:list"
# Args: ["--verbose"]
```

**Pattern 2: Compound name**

```bash
cpm plugin list --verbose
# Tokens: ["plugin", "list", "--verbose"]
# Check: "plugin:list" exists? Yes
# Spec: "plugin:list"
# Args: ["--verbose"]
```

**Pattern 3: Simple name**

```bash
cpm init
# Tokens: ["init"]
# Spec: "init"
# Args: []
```

### Resolution Algorithm

```python
def _extract_command_spec(args: Sequence[str], qualified_names: set[str]) -> tuple[str, list[str]]:
    """
    Extract command spec and remaining args.

    1. If first token contains ":" and is in qualified_names → use it
    2. If first+second form "group:name" in qualified_names → use it
    3. Otherwise → use first token as simple name
    """
    first, *rest = args

    # Check qualified
    if ":" in first and first in qualified_names:
        return first, list(rest)

    # Check compound
    if rest:
        maybe = f"{first}:{rest[0]}"
        if maybe in qualified_names:
            return maybe, list(rest[1:])

    # Simple name
    return first, list(rest)
```

### Ambiguous Names

If multiple features share a simple name:

```bash
cpm build
# Error: Command is ambiguous (cpm:build, plugin:build); use group:name to disambiguate.
```

Use qualified names:

```bash
cpm cpm:build       # Core builder
cpm plugin:build    # Plugin builder
```

---

## Special Handling

### Embed Commands

Embed commands are delegated to `cpm_cli/cli.py`:

```bash
cpm embed add --name local --url http://127.0.0.1:8876
# Handled by: cpm_cli/cli.py:build_parser()
```

**Supported embed commands:**

- `cpm embed add` - Register provider
- `cpm embed remove` - Remove provider
- `cpm embed set-default` - Select default provider
- `cpm embed test` - Validate provider connectivity
- `cpm embed status` - Check server status

### Legacy Commands

Legacy tokens are mapped for backward compatibility:

| Legacy Token | Modern Equivalent                |
|--------------|----------------------------------|
| `lookup`     | `pkg:list`                       |
| `use`        | `pkg:use`                        |
| `prune`      | `pkg:prune`                      |
| `mcp`        | `serve` (if followed by "serve") |

**Example:**

```bash
cpm lookup           # Mapped to: cpm pkg:list
cpm use pkg@1.0.0    # Mapped to: cpm pkg:use pkg@1.0.0
```

**Legacy delegation:**

Compatibility aliases currently cover:
- `lookup` -> `pkg list`
- `use` -> `pkg use`
- `prune` -> `pkg prune`
- `mcp serve` -> `serve`

---

## CLI Entry Point

### main()

```python
def main(
        argv: Sequence[str] | None = None,
        *,
        start_dir: Path | str | None = None,
) -> int:
    """
    Main CLI entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])
        start_dir: Starting directory for workspace resolution

    Returns:
        Exit code (0 = success, non-zero = error)
    """
```

**Flow:**

1. Parse tokens from `argv`
2. Handle special cases (`--help`, `--version`, `embed`, legacy)
3. Bootstrap `CPMApp`
4. Extract command spec
5. Resolve via `FeatureRegistry`
6. Configure `ArgumentParser`
7. Parse arguments
8. Instantiate and run command
9. Return exit code

---

## Help Output

### Overview (cpm help)

```bash
$ cpm help

Usage: cpm <command> [args...]

Core commands:
  init                           Initialize CPM workspace
  help                           Show this help message
  listing                        List all commands
  doctor                         Validate workspace and configuration

Plugin commands:
  mcp:serve                      Start MCP server
  plugin:list                    List loaded plugins
  plugin:doctor                  Diagnose plugin issues

Use group:name to disambiguate commands when needed.
```

### Detailed Help (cpm help --long)

```bash
$ cpm help --long

Usage: cpm <command> [args...]

Core commands:
  init                           Initialize CPM workspace
    Creates .cpm/ directory structure and default configuration files.

  help                           Show this help message
    Display available commands with descriptions.
    Use --long for detailed output.

  listing                        List all commands
    List registered commands in plain text or JSON format.
    ...
```

### Command-Specific Help

```bash
$ cpm plugin:list --help

usage: cpm plugin:list [-h] [--include-builtin]

List loaded plugins.

options:
  -h, --help         show this help message and exit
  --include-builtin  Include core plugin in output
```

---

## Error Handling

### Feature Not Found

```bash
$ cpm nonexistent
nonexistent is not registered.
```

### Ambiguous Feature

```bash
$ cpm build
Command is ambiguous (cpm:build, plugin:build); use group:name to disambiguate.
```

### Argument Parsing Error

```bash
$ cpm init --invalid-flag
usage: cpm init [-h]
cpm init: error: unrecognized arguments: --invalid-flag
```

---

## Integration with cpm_core

```python
from cpm_core.app import CPMApp

# Bootstrap app (loads workspace, builtins, plugins)
app = CPMApp(start_dir=".")
app.bootstrap()

# Resolve command
entry = app.feature_registry.resolve("init")

# Instantiate and run
command = entry.target()
result = command.run(args)
```

---

## Testing

```python
from cpm_cli.main import main


def test_init_command():
    result = main(["init"])
    assert result == 0


def test_help_command():
    result = main(["help"])
    assert result == 0


def test_unknown_command():
    result = main(["nonexistent"])
    assert result == 1
```

---

## See Also

- [cpm_core/README.md](../cpm_core/README.md) - Core foundation
- [cpm_core/registry/README.md](../cpm_core/registry/README.md) - Feature Registry
- [cpm_core/api/README.md](../cpm_core/api/README.md) - Command interfaces

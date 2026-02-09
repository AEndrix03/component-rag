# cpm_builtin/packages - Package Management System

**Version-aware package management with pinning, activation, and pruning.**

The package management system provides utilities for installing, versioning, activating, and pruning context packet installations in a CPM workspace.

---

## Quick Start

```python
from cpm_builtin.packages.manager import PackageManager

manager = PackageManager(workspace_root=".cpm")

# List installed packages
for summary in manager.list_packages():
    print(f"{summary.name} @ {summary.active_version}")
    print(f"  Versions: {', '.join(summary.versions)}")
    print(f"  Pinned: {summary.pinned_version}")

# Use (pin and activate) a specific version
manager.use("my-package@1.2.0")

# Prune old versions (keep latest 2)
removed = manager.prune("my-package", keep=2)
print(f"Removed: {removed}")
```

---

## Architecture Overview

```
cpm_builtin/packages/
├── manager.py      # PackageManager, PackageSummary
├── layout.py       # Directory structure helpers
├── versions.py     # Version parsing and comparison
└── io.py           # YAML I/O utilities
```

---

## Directory Structure

Packages are stored with semantic versioning:

```
.cpm/
├── packages/
│   ├── python-stdlib/
│   │   ├── 1.0.0/
│   │   │   ├── manifest.json
│   │   │   ├── docs.jsonl
│   │   │   ├── faiss/
│   │   │   └── cpm.yml
│   │   ├── 1.1.0/
│   │   └── 1.2.0/
│   └── react-docs/
│       ├── 18.0.0/
│       └── 18.2.0/
├── state/
│   ├── pins/
│   │   ├── python-stdlib.yml  # Pinned version
│   │   └── react-docs.yml
│   └── active/
│       ├── python-stdlib.yml  # Active version
│       └── react-docs.yml
```

**Key Files:**

- `packages/{name}/{version}/`: Version directory
- `state/pins/{name}.yml`: Pinned version (explicit user preference)
- `state/active/{name}.yml`: Active version (currently in use)

---

## PackageManager

Central API for package operations:

```python
from cpm_builtin.packages.manager import PackageManager
from pathlib import Path

manager = PackageManager(workspace_root=Path(".cpm"))
```

### List Packages

```python
from cpm_builtin.packages.manager import PackageSummary

summaries: list[PackageSummary] = manager.list_packages()

for summary in summaries:
    print(f"Name: {summary.name}")
    print(f"Versions: {summary.versions}")
    print(f"Pinned: {summary.pinned_version}")
    print(f"Active: {summary.active_version}")
```

**PackageSummary:**

```python
@dataclass(frozen=True)
class PackageSummary:
    name: str                        # Package name
    versions: Sequence[str]          # Installed versions (sorted)
    pinned_version: str | None       # User-pinned version
    active_version: str | None       # Currently active version
```

### Installed Versions

```python
versions = manager.installed_versions("python-stdlib")
print(versions)  # ["1.0.0", "1.1.0", "1.2.0"]
```

### Pinned Version

```python
# Get pinned version
pinned = manager.get_pinned_version("python-stdlib")
print(pinned)  # "1.2.0" or None

# Set pinned version
manager.set_pinned_version("python-stdlib", "1.2.0")
```

### Active Version

```python
# Get active version
active = manager.get_active_version("python-stdlib")
print(active)  # "1.2.0" or None

# Set active version
manager.set_active_version("python-stdlib", "1.2.0")
```

### Version Resolution

```python
# Resolve version based on target
resolved = manager.resolve_version("python-stdlib", target="latest")
# Returns latest installed version

resolved = manager.resolve_version("python-stdlib", target="1.1.0")
# Returns "1.1.0" if installed, else raises ValueError

resolved = manager.resolve_version("python-stdlib", target=None)
# Returns pinned version if set, else latest
```

**Resolution Logic:**

1. If `target` is `None`:
   - Return pinned version if set and installed
   - Otherwise, return latest installed version
2. If `target` is `"latest"`:
   - Return latest installed version
3. If `target` is a specific version:
   - Return that version if installed
   - Otherwise, raise `ValueError`

### Use (Pin and Activate)

```python
# Use latest version
resolved = manager.use("python-stdlib")
print(resolved)  # "1.2.0"

# Use specific version
resolved = manager.use("python-stdlib@1.1.0")
print(resolved)  # "1.1.0"

# Alternative syntax
resolved = manager.use(name="python-stdlib", version="1.1.0")
```

**Effect:**
- Sets pinned version
- Sets active version
- Returns resolved version

### Prune Old Versions

```python
# Keep latest 2 versions
removed = manager.prune("python-stdlib", keep=2)
print(removed)  # ["1.0.0"]

# Keep latest 1 (default)
removed = manager.prune("python-stdlib", keep=1)
print(removed)  # ["1.0.0", "1.1.0"]
```

**Prune Logic:**

1. Sort versions by semantic version
2. Keep latest N versions
3. Preserve pinned version (even if older)
4. Preserve active version (even if older)
5. Delete remaining versions

### Remove Package

```python
# Remove all versions and metadata
manager.remove("python-stdlib")
```

**Effect:**
- Deletes `packages/python-stdlib/`
- Deletes `state/pins/python-stdlib.yml`
- Deletes `state/active/python-stdlib.yml`

---

## Version Parsing and Comparison

### parse_package_spec

Parse package specification strings:

```python
from cpm_builtin.packages.manager import parse_package_spec

name, version = parse_package_spec("python-stdlib@1.2.0")
# ("python-stdlib", "1.2.0")

name, version = parse_package_spec("react-docs")
# ("react-docs", None)

name, version = parse_package_spec("my-pkg@latest")
# ("my-pkg", "latest")
```

### Version Comparison

Versions are compared using semantic versioning with custom extensions:

```python
from cpm_builtin.packages.versions import version_key

versions = ["1.0.0", "1.2.0-beta.1", "1.1.0", "1.2.0", "2.0.0-alpha.3"]
sorted_versions = sorted(versions, key=version_key)
print(sorted_versions)
# ["1.0.0", "1.1.0", "1.2.0-beta.1", "1.2.0", "2.0.0-alpha.3"]
```

**Supported Formats:**

- Semantic versioning: `1.2.3`
- Pre-release qualifiers: `1.2.3-alpha.1`, `1.2.3-beta.2`, `1.2.3-rc.1`
- Build metadata: `1.2.3+build.123`
- Stage keywords: `dev`, `snapshot`, `nightly`, `alpha`, `beta`, `rc`, `stable`, `final`

**Stage Priority (lowest to highest):**

```python
STAGE_ORDER = {
    "dev": 0,
    "snapshot": 0,
    "nightly": 0,
    "a": 10, "alpha": 10,
    "b": 20, "beta": 20,
    "pre": 30, "preview": 30,
    "rc": 40, "candidate": 40,
    "stable": 90, "release": 90,
    "final": 100,
}
```

### split_version_parts

```python
from cpm_builtin.packages.versions import split_version_parts

parts = split_version_parts("1.2.3-beta.1")
# ["1", "2", "3-beta", "1"]

parts = split_version_parts("2.0.0-rc.5+build.123")
# ["2", "0", "0-rc", "5+build", "123"]
```

---

## Usage Examples

### Example 1: List All Packages

```python
from cpm_builtin.packages.manager import PackageManager

manager = PackageManager(".cpm")

summaries = manager.list_packages()

print(f"Found {len(summaries)} packages:")
for summary in summaries:
    active = summary.active_version or "none"
    print(f"\n{summary.name} (active: {active})")
    for version in summary.versions:
        marker = " [active]" if version == summary.active_version else ""
        marker += " [pinned]" if version == summary.pinned_version else ""
        print(f"  - {version}{marker}")
```

### Example 2: Install and Activate

```python
# Assume package was built into .cpm/packages/my-docs/1.0.0/

manager = PackageManager(".cpm")

# List versions
versions = manager.installed_versions("my-docs")
print(f"Installed: {versions}")  # ["1.0.0"]

# Activate latest
resolved = manager.use("my-docs")
print(f"Active: {resolved}")  # "1.0.0"

# Check active version
active = manager.get_active_version("my-docs")
print(f"Active version: {active}")  # "1.0.0"
```

### Example 3: Multi-Version Management

```python
manager = PackageManager(".cpm")

# Install multiple versions (done by build command)
# .cpm/packages/python-stdlib/1.0.0/
# .cpm/packages/python-stdlib/1.1.0/
# .cpm/packages/python-stdlib/1.2.0/

# List versions
versions = manager.installed_versions("python-stdlib")
print(versions)  # ["1.0.0", "1.1.0", "1.2.0"]

# Pin specific version
manager.use("python-stdlib@1.1.0")

# Verify pinned
pinned = manager.get_pinned_version("python-stdlib")
print(f"Pinned: {pinned}")  # "1.1.0"

# Prune old versions (keep 2)
removed = manager.prune("python-stdlib", keep=2)
print(f"Removed: {removed}")  # ["1.0.0"]

# Verify remaining
versions = manager.installed_versions("python-stdlib")
print(versions)  # ["1.1.0", "1.2.0"]
```

### Example 4: Version Resolution

```python
manager = PackageManager(".cpm")

# Installed: 1.0.0, 1.1.0, 1.2.0
# Pinned: 1.1.0

# Resolve without target (uses pinned)
resolved = manager.resolve_version("python-stdlib")
print(resolved)  # "1.1.0"

# Resolve latest
resolved = manager.resolve_version("python-stdlib", "latest")
print(resolved)  # "1.2.0"

# Resolve specific
resolved = manager.resolve_version("python-stdlib", "1.0.0")
print(resolved)  # "1.0.0"

# Try to resolve non-existent version
try:
    resolved = manager.resolve_version("python-stdlib", "2.0.0")
except ValueError as e:
    print(e)  # "version 2.0.0 is not installed for python-stdlib"
```

### Example 5: Safe Pruning

```python
manager = PackageManager(".cpm")

# Installed: 0.9.0, 1.0.0, 1.1.0, 1.2.0, 1.3.0
# Pinned: 1.0.0
# Active: 1.0.0

# Prune keeping latest 2
removed = manager.prune("my-pkg", keep=2)
print(removed)  # ["0.9.0", "1.1.0"]

# Preserved: 1.0.0 (pinned/active), 1.2.0, 1.3.0
versions = manager.installed_versions("my-pkg")
print(versions)  # ["1.0.0", "1.2.0", "1.3.0"]
```

---

## Integration with Build System

### Building Packages

```python
from cpm_core.build.builder import DefaultBuilder
from cpm_builtin.packages.manager import PackageManager

# Build packet
builder = DefaultBuilder()
manifest = builder.build(
    source="./docs",
    destination=".cpm/packages/my-docs/1.0.0",
)

# Activate the built package
manager = PackageManager(".cpm")
manager.use("my-docs@1.0.0")
```

### Querying Packages

```python
from cpm_builtin.packages.manager import PackageManager

manager = PackageManager(".cpm")

# Resolve package to query
version = manager.resolve_version("python-stdlib")
package_dir = f".cpm/packages/python-stdlib/{version.replace('.', '/')}"

# Load FAISS index and query
# (see cpm_plugins/mcp for query implementation)
```

---

## cpm.yml Format

Each package version has a `cpm.yml` file:

```yaml
# .cpm/packages/python-stdlib/1.2.0/cpm.yml
name: python-stdlib
version: 1.2.0
description: Python standard library documentation
tags: python, stdlib, docs
entrypoints: sys, os, pathlib, re
embedding_model: jinaai/jina-embeddings-v2-base-code
embedding_dim: 768
embedding_normalized: true
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Package name |
| `version` | string | Yes | Semantic version |
| `description` | string | No | Human-readable description |
| `tags` | CSV | No | Comma-separated tags |
| `entrypoints` | CSV | No | Key modules/topics |
| `embedding_model` | string | No | Embedding model used |
| `embedding_dim` | int | No | Embedding dimension |
| `embedding_normalized` | bool | No | Whether embeddings are normalized |

---

## Directory Layout Helpers

The `layout.py` module provides path utilities:

```python
from cpm_builtin.packages.layout import (
    packages_root,
    pins_root,
    active_root,
    version_dir,
)
from pathlib import Path

workspace = Path(".cpm")

# Get directories
packages = packages_root(workspace)  # .cpm/packages
pins = pins_root(workspace)          # .cpm/state/pins
active = active_root(workspace)      # .cpm/state/active

# Version directory
vdir = version_dir(workspace, "python-stdlib", "1.2.0")
# .cpm/packages/python-stdlib/1/2/0
```

---

## Versioning Strategy

### Semantic Versioning

CPM uses semantic versioning with extensions:

- `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- Pre-release: `1.2.3-alpha.1`, `1.2.3-beta.2`, `1.2.3-rc.1`
- Build metadata: `1.2.3+build.123`

### Version Resolution

1. **Pinned version**: Explicit user preference
2. **Active version**: Currently loaded version
3. **Latest version**: Highest semantic version

### Version Directory Structure

Versions are stored as nested directories:

```
.cpm/packages/python-stdlib/
├── 1/0/0/          # Version 1.0.0
├── 1/1/0/          # Version 1.1.0
└── 1/2/0/          # Version 1.2.0
```

This structure:
- Avoids filesystem issues with dots in filenames
- Enables efficient version traversal
- Supports deep version hierarchies

---

## Best Practices

### 1. Pin Important Versions

```python
# Pin production version
manager.use("my-package@1.2.0")
```

### 2. Prune Regularly

```python
# Keep 3 latest versions
for summary in manager.list_packages():
    manager.prune(summary.name, keep=3)
```

### 3. Check Before Removal

```python
summary = next(
    (s for s in manager.list_packages() if s.name == "my-pkg"),
    None
)
if summary and summary.active_version:
    print(f"Warning: {summary.name} is active")
```

### 4. Use Latest for Development

```python
# Development: always use latest
manager.use("dev-docs@latest")

# Production: pin specific version
manager.use("prod-docs@1.2.0")
```

---

## Testing

```bash
# Run all package tests
pytest cpm_builtin/packages/

# Test manager
pytest cpm_builtin/packages/test_manager.py -v

# Test versions
pytest cpm_builtin/packages/test_versions.py -v
```

---

## See Also

- [cpm_builtin/README.md](../README.md) - Built-in features overview
- [cpm_core/build/README.md](../../cpm_core/build/README.md) - Build system
- [cpm_core/packet/README.md](../../cpm_core/packet/README.md) - Packet structure
- [cpm_plugins/mcp/README.md](../../cpm_plugins/mcp/README.md) - MCP plugin (uses PackageManager)

# CPM Documentation Index

**Complete documentation structure for Context Packet Manager.**

---

## Main Documentation

📘 **[README.md](./README.md)** - Project overview, installation, quick start, and feature highlights

---

## Core Foundation (cpm_core)

📂 **[cpm_core/README.md](./cpm_core/README.md)** - Foundation layer overview

- CPMApp orchestrator
- Workspace management
- ServiceContainer DI
- EventBus
- ConfigStore
- PluginManager

### Core Sub-Packages

📂 **[cpm_core/api/README.md](./cpm_core/api/README.md)** - Abstract interfaces

- CPMAbstractCommand
- CPMAbstractBuilder
- CPMAbstractRetriever
- @cpmcommand decorator
- Implementation examples

📂 **[cpm_core/plugin/README.md](./cpm_core/plugin/README.md)** - Plugin system

- PluginManager
- PluginManifest
- PluginLoader
- PluginContext
- Plugin lifecycle
- Discovery algorithm

📂 **[cpm_core/registry/README.md](./cpm_core/registry/README.md)** - Feature Registry

- FeatureRegistry
- CPMRegistryEntry
- Name resolution
- Disambiguation strategy
- RegistryClient

📂 **[cpm_core/builtins/README.md](./cpm_core/builtins/README.md)** - Built-in commands

- InitCommand (cpm:init)
- HelpCommand (cpm:help)
- ListingCommand (cpm:listing)
- PluginListCommand (plugin:list)
- PluginDoctorCommand (plugin:doctor)

📂 **[cpm_core/build/README.md](./cpm_core/build/README.md)** - Build system

- DefaultBuilder
- Build workflow
- Incremental caching
- Source scanning
- Embedding integration

📂 **[cpm_core/packet/README.md](./cpm_core/packet/README.md)** - Packet structures

- DocChunk
- PacketManifest
- EmbeddingSpec
- FaissFlatIP
- I/O utilities

---

## CLI Routing (cpm_cli)

📂 **[cpm_cli/README.md](./cpm_cli/README.md)** - CLI routing layer

- Command resolution
- Token extraction
- Legacy compatibility
- Error handling
- Help output

---

## Built-in Features (cpm_builtin)

📂 **[cpm_builtin/README.md](./cpm_builtin/README.md)** - Built-in features overview

- Architecture patterns
- Command implementations
- Feature organization

### Built-in Sub-Packages

📂 **[cpm_builtin/chunking/README.md](./cpm_builtin/chunking/README.md)** - Chunking strategies

- ChunkerRouter (auto/multi mode)
- python_ast chunker
- java chunker
- markdown chunker
- text chunker
- treesitter_generic chunker (40+ languages)
- brace_fallback chunker
- Hierarchical chunking
- Token budget system
- Configuration options

📂 **[cpm_builtin/embeddings/README.md](./cpm_builtin/embeddings/README.md)** - Embedding system

- EmbeddingProviderConfig
- EmbeddingsConfigService
- HttpEmbeddingConnector
- Authentication (bearer, basic)
- Provider management
- YAML configuration

📂 **[cpm_builtin/packages/README.md](./cpm_builtin/packages/README.md)** - Package management

- PackageManager
- PackageSummary
- Directory layout
- Version resolution
- Package lifecycle
- Semantic versioning

---

## Official Plugins (cpm_plugins)

📂 **[cpm_plugins/README.md](./cpm_plugins/README.md)** - Official plugins overview

- Plugin structure examples
- Development guide

### MCP Plugin

📂 **[cpm_plugins/mcp/README.md](./cpm_plugins/mcp/README.md)** - MCP Plugin

- Architecture
- MCPServeCommand
- FastMCP tools (lookup, query)
- PacketRetriever
- PacketReader
- Claude Desktop integration
- Configuration examples

---

## Legacy Components

📂 **[registry/README.md](./registry/README.md)** - CPM Registry (legacy)

---

## Documentation Organization

### By User Journey

**Getting Started:**

1. [README.md](./README.md) - Installation and quick start
2. [cpm_core/README.md](./cpm_core/README.md) - Core concepts
3. [cpm_cli/README.md](./cpm_cli/README.md) - CLI usage

**Creating Plugins:**

1. [cpm_core/api/README.md](./cpm_core/api/README.md) - Interfaces
2. [cpm_core/plugin/README.md](./cpm_core/plugin/README.md) - Plugin system
3. [cpm_plugins/README.md](./cpm_plugins/README.md) - Examples

**Building Packets:**

1. [cpm_builtin/chunking/README.md](./cpm_builtin/chunking/README.md) - Chunking
2. [cpm_builtin/embeddings/README.md](./cpm_builtin/embeddings/README.md) - Embeddings
3. [cpm_core/build/README.md](./cpm_core/build/README.md) - Build process

**Managing Packets:**

1. [cpm_builtin/packages/README.md](./cpm_builtin/packages/README.md) - Package management
2. [cpm_core/packet/README.md](./cpm_core/packet/README.md) - Packet structure

**Integration:**

1. [cpm_plugins/mcp/README.md](./cpm_plugins/mcp/README.md) - MCP integration
2. [README.md#mcp-integration](./README.md#model-context-protocol-mcp-integration) - Claude Desktop setup

---

## Quick Reference

### Command Reference

- **Core**: init, help, listing, doctor
- **Plugin**: plugin:list, plugin:doctor
- **Package**: pkg:list, pkg:use, pkg:prune
- **Build**: build
- **Query**: query (legacy)
- **Embed**: embed add/list/remove/set-default/test
- **MCP**: mcp:serve

### Configuration Files

- `.cpm/config/cpm.toml` - Main configuration
- `.cpm/config/embeddings.yml` - Embedding providers
- `plugin.toml` - Plugin manifest

### Environment Variables

- `RAG_CPM_DIR` - Workspace root (default: `.cpm`)
- `RAG_EMBED_URL` - Embedding server URL (default: `http://127.0.0.1:8876`)
- `CPM_CONFIG` - Config file path
- `CPM_EMBEDDINGS` - Embeddings config path

---

## Documentation Standards

All README files follow these conventions:

1. **Structure**:
    - Quick Start section with minimal example
    - Architecture/Components overview
    - Detailed API documentation
    - Usage examples
    - See Also references

2. **Code Examples**:
    - Syntax-highlighted Python code blocks
    - Commented code where helpful
    - Both CLI and programmatic examples

3. **Cross-References**:
    - Links to related documentation
    - Links use relative paths
    - "See Also" sections at the end

4. **Style**:
    - Professional, concise tone
    - Active voice
    - Clear headings with consistent hierarchy
    - Tables for structured information
    - ASCII diagrams where helpful

---

## Contributing to Documentation

When adding new features:

1. Update the relevant README in the component's directory
2. Add examples showing the new feature
3. Update this index if adding new components
4. Cross-reference related documentation
5. Follow existing documentation patterns

---

## Getting Help

- Check the relevant README for your component
- Use `cpm doctor` to diagnose issues
- Use `cpm help --long` for detailed command help
- Review examples in `cpm_plugins/` for plugin development

---

**Last Updated**: 2026-02-05
**Documentation Version**: 1.0.0
**CPM Version**: (0.1.0)

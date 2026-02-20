# cpm_cli - CLI Routing Layer

`cpm_cli` is the runtime dispatcher for CPM commands.
It bootstraps `CPMApp`, resolves the command against `FeatureRegistry`, builds an `argparse` parser for the resolved feature, and executes it.

## Quick Start

```bash
cpm help
cpm init
cpm build --help
cpm query --help
cpm embed add --help
cpm plugin:list
cpm plugin:doctor
```

## Resolution Model

The CLI resolves commands from user tokens in this order:

1. qualified token (`group:name`), e.g. `plugin:list`
2. compound token (`group name`), e.g. `plugin list` -> `plugin:list`
3. simple token (`name`), e.g. `query`

If a simple token is ambiguous, CPM returns an error and requires `group:name`.

## Dispatch Flow

1. Parse argv tokens (`cpm_cli.main.main`)
2. Handle `--help` / `--version` shortcuts
3. Bootstrap `CPMApp` (workspace + builtins + plugins)
4. Resolve command entry from `FeatureRegistry`
5. Build command-specific `ArgumentParser`
6. Parse command arguments
7. Instantiate command class and call `run(args)`

## Help and Listing

```bash
cpm help
cpm help --long
cpm listing
cpm listing --format json
```

`cpm help` prints grouped command overview.
`cpm listing` prints a compact command list in text or JSON format.

## Plugin Command Access

Both forms are supported:

```bash
cpm plugin:list
cpm plugin list

cpm plugin:doctor
cpm plugin doctor
```

## Error Modes

Unknown command:

```bash
cpm nonexistent
```

Ambiguous command name:

```bash
cpm <ambiguous-name>
```

Argument parsing errors are emitted by the selected command parser.

## Entrypoint

`pyproject.toml` wires the console script:

- `cpm = "cpm_cli.__main__:main"`

## Related Docs

- [cpm_core/README.md](../cpm_core/README.md)
- [cpm_core/registry/README.md](../cpm_core/registry/README.md)
- [cpm_core/api/README.md](../cpm_core/api/README.md)

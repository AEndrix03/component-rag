# MCP Tool: `lookup`

Remote-first packet lookup optimized for low token/network cost.

## When to use

- discover/select a packet
- inspect packet metadata (version, alias, capabilities, entrypoints, kind, compat)
- get a digest-pinned ref for later retrieval

Do not use `query` for metadata-only requests.

## Behavior

1. Build `source_uri` from `ref` or (`REGISTRY` + `name` + `version/alias`).
2. Resolve metadata through core `SourceResolver.lookup_metadata(...)`.
3. Apply filters (`entrypoint`, `kind`, `capability`, `os`, `arch`).
4. Return deterministic shortlist (`max 3`) with `pinned_uri`.

The resolver path is OCI metadata-only:

- resolve digest
- fetch manifest
- fetch metadata blob (`application/vnd.cpm.packet.manifest.v1+json`)

## Input

- `name` (required unless `ref` contains full packet reference)
- `version` or `alias` (default `latest`)
- optional `entrypoint`, `kind`, `capability`, `os_name`, `arch`
- optional `registry`, `ref`, `k`, `cpm_root`

## Output

- `selected`: first candidate
- `candidates`: up to 3
- each candidate includes `pinned_uri`, `name`, `version`, `entrypoints`, `tags`, `kind`, `capabilities`

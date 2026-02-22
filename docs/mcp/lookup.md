# `cpm lookup` for MCP

## Low-Token Resolver Path

Remote lookup resolves packet metadata without pulling payload:

1. resolve reference digest
2. fetch OCI manifest
3. fetch metadata blob (`packet.manifest.json` layer)
4. validate metadata schema
5. filter and select entrypoint
6. return digest-pinned URI

## Inputs

- `--source-uri oci://...`
- or `--registry` + `--name` + (`--version` or `--alias`)
- optional filters:
  - `--kind`
  - `--entrypoint`
  - `--capability` (repeatable)
  - `--os`
  - `--arch`

## Catalog-assisted Lookup

- `--use-catalog`
- local catalog via `--catalog-file`
- OCI catalog via `--catalog-ref`

## Output

- digest-pinned URI (`oci://repo/name@sha256:...`)
- selected entrypoint
- packet metadata summary

For JSON clients use `--format json`.

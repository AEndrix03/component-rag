# Packet Metadata v1

Schema file: `schemas/packet-metadata/v1.json`

## Identity

- `schema`: `cpm.packet.metadata`
- `schema_version`: `1.0`

## Core Fields

- `packet`
  - `name`, `version`
  - optional: `description`, `tags`, `kind`, `entrypoints`, `capabilities`
- `compat` (optional)
  - `os`, `arch`, `cpm_min_version`
- `payload`
  - `files[]` with `name`, optional `digest`, optional `size`
  - optional `full_ref`
- `source` (optional)
  - `manifest_digest`
  - `build` options (`minimal`, `include_docs`, `include_embeddings`)

## Determinism Rules

- metadata JSON is serialized with stable key ordering
- payload entries include digest/size to support integrity checks
- metadata remains small by default (full source manifest omitted)

## Legacy Compatibility

If `schema: cpm-oci/v1` is encountered, lookup normalizes it to metadata v1 shape before filtering.

# `cpm publish`

## Purpose

Package a built packet directory into an OCI artifact and push it to a registry.

## Main Flags

- `--from-dir <path>` packet directory (required)
- `--registry <repo>` OCI repository base (`registry.local/project`)
- `--insecure` allow insecure TLS

### Payload Modes

- `--minimal`
  - minimal publish: excludes docs and embeddings
- `--full`
  - explicit full mode (mutually exclusive with `--minimal`)
- `--with-docs` / `--no-docs`
- `--with-embeddings` / `--no-embeddings`
- `--no-embed`
  - backward-compatible alias to disable embeddings

## Output Format

`cpm publish` emits:

- packet name/version
- pushed ref
- digest
- mode summary for minimal/custom payload settings

## OCI Artifact Content

- always includes `packet.manifest.json` metadata layer
- includes `packet.lock.json` if present in packet dir
- includes `payload/` content according to selected flags

# OCI Overview

## Current Artifact Contract

`cpm publish` builds an OCI artifact with:

- `packet.manifest.json` metadata layer (`application/vnd.cpm.packet.manifest.v1+json`)
- `packet.lock.json` optional lock layer (`application/vnd.cpm.packet.lock.v1+json`)
- `payload/` files (`cpm.yml`, `manifest.json`, optional `docs.jsonl`, optional embeddings/faiss)

The metadata layer is now schema-versioned (`cpm.packet.metadata` v`1.0`) and intentionally small to support lookup with:

1. OCI manifest fetch
2. metadata blob fetch

No payload download is required for standard lookup.

## Publish Modes

- `--minimal`: metadata + minimal payload (`cpm.yml`, `manifest.json`)
- default/full: metadata + payload (docs and embeddings enabled by default)
- payload toggles:
  - `--with-docs` / `--no-docs`
  - `--with-embeddings` / `--no-embeddings`
  - legacy `--no-embed` remains supported

## Compatibility

- Legacy metadata (`schema: cpm-oci/v1`) is normalized at lookup-time.
- If metadata layer is missing, resolver falls back to artifact pull and legacy metadata extraction.
- `install` falls back to `payload/manifest.json` when `source_manifest` is not present in metadata.

## OCI Publish vs Image

The publish output is an OCI artifact carrying CPM packet data. It is not a runnable container image and has no runtime entrypoint like Docker images.

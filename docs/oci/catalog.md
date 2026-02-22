# OCI Catalog

## Purpose

Provide scalable search without registry-wide enumeration by publishing a downloadable catalog blob.

## Command

`cpm catalog`:

- scans local packages (default `./.cpm/packages`)
- writes `cpm-catalog.jsonl`
- optionally publishes the catalog as OCI artifact via `--publish-ref`

Catalog media type:

- `application/vnd.cpm.catalog.v1+jsonl`

## Typical Flow

1. build catalog:
   - `cpm catalog --format json`
2. publish catalog:
   - `cpm catalog --publish-ref registry.local/project/cpm/catalog:latest`
3. lookup with catalog:
   - `cpm lookup --use-catalog --catalog-ref oci://registry.local/project/cpm/catalog:latest --registry ... --name ...`

Each JSONL row is one packet version candidate.

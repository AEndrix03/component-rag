# OCI Compatibility

## Backward Compatibility Rules

- Metadata v1 (`cpm.packet.metadata`) is the primary lookup contract.
- Legacy metadata (`cpm-oci/v1`) remains readable through normalization.
- If metadata layer is missing, resolver falls back to legacy artifact pull.
- `install` supports metadata without `source_manifest` by reading `payload/manifest.json`.

## Registry Interop Notes

- ORAS client is used for resolve, manifest/blob fetch, pull, push, and referrers discovery.
- Domain allowlist and auth options are enforced centrally.
- Digest-based metadata cache reduces repeated remote requests.

## Migration Guidance

- Prefer `--minimal` for lookup-first artifact distribution.
- Keep `--no-embed` temporarily for older scripts, migrate to `--no-embeddings`.
- Adopt `packet.manifest.json` metadata v1 as canonical metadata source.

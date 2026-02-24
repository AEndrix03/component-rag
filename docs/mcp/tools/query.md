# MCP Tool: `query`

Cache-first query with lazy OCI materialization on miss.

## When to use

- answer a semantic/content question using packet snippets
- retrieve evidence after `lookup` selected a packet (`selected.pinned_uri`)

Do not use `query` to discover packets or inspect metadata (use `lookup`).

## Behavior

1. Resolve `source_uri` from `ref` (or `REGISTRY + ref`).
2. Cache probe using digest paths under `CPM_ROOT`.
3. On hit: run retrieval immediately.
4. On miss:
   - `SourceResolver.resolve_and_fetch(...)`
   - mirror payload into `cas/<digest>/payload`
   - ensure index in `index/<digest>/<embedding_fingerprint>`
   - reuse precomputed `faiss/index.faiss` and `vectors.f16.bin` when present
   - fallback to on-the-fly indexing from `docs.jsonl` when missing
5. Return token-minimal snippet list.

## Input

- `ref`: `pinned_uri` (recommended) or packet ref (`name@version`, `name:alias`)
- `q`: query text
- optional `k` (max 20), `registry`, `cpm_root`

## Output

- `cache.hit`: `true/false`
- `pinned_uri`, `digest`
- `results[]`: `{score, path, start, end, snippet}`

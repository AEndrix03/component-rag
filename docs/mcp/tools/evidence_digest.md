# MCP Tool: `evidence_digest`

Compressed retrieval evidence for downstream reasoning.

## Strategy

1. Run `query`.
2. Deduplicate snippets (`path + snippet`).
3. Trim by `max_chars`.
4. Return compact `evidence` and short `summary`.

## Input

- `ref`
- `question`
- optional `k` (default 6), `max_chars` (default 1200), `registry`, `cpm_root`

## Output

- `evidence[]`: compressed snippets with citations (`path`, offsets when available)
- `summary`: short deterministic technical digest

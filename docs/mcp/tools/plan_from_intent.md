# MCP Tool: `plan_from_intent`

Intent planner that minimizes tool thrashing.

## Strategy

1. Candidate generation from `name_hint` / `constraints.name` (or `packet:<name>` in intent).
2. Intent classification: `lookup` (metadata/discovery) vs `query` (semantic retrieval).
3. Metadata-first scoring (`entrypoint`, `kind`, `capabilities`).
4. Query-only on tie for top candidates, and only for `intent_mode=query`.
4. Deterministic output plan with selected + fallback.

## Input

- `intent` (required)
- optional `constraints` object
- optional `name_hint`, `version`, `registry`, `cpm_root`

## Output

- `intent_mode`: `lookup` or `query`
- `selected[]`: `{pinned_uri, entrypoint, args_template, why}`
- `fallbacks[]`
- `constraints_applied`

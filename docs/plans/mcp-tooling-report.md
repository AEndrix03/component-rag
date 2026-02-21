# MCP Tooling Report (CPM)

## Objective
Define high-impact MCP tools that let an LLM use CPM end-to-end (discovery, trust, retrieval, explainability), and close the current gap where `lookup` is local-only.

## Current State (as-is)

### Strong points already available
- CLI `query` already supports lazy OCI registry resolution via `--registry`/`--source`, trust verification, policy checks, and replay logging (`cpm_core/builtins/query.py`).
- Source resolver has OCI resolution, trust evaluation, and CAS materialization (`cpm_core/sources/resolver.py`).
- MCP server exists and is easy to run via `mcp:serve` (`cpm_plugins/mcp/cpm_mcp_plugin/features.py`).

### Main gaps for LLM workflows
- `lookup` builtin is local filesystem inventory only (`--destination` under workspace), no registry mode (`cpm_core/builtins/lookup.py`).
- MCP `lookup` is also local-only (`PacketReader.list_packets`), no remote discovery (`cpm_plugins/mcp/cpm_mcp_plugin/server.py`).
- MCP `query` uses a simplified local `PacketRetriever` pipeline and does not expose full query capabilities (registry lazy source, policy/trust context, hybrid indexer/reranker, replay metadata).
- Hub client currently exposes only remote policy evaluation (`cpm_core/hub/client.py`), no remote package discovery/search endpoint usage in CPM core.

## Proposed MCP Tools (priority order)

### P0 - Core value for agents
1. `cpm_lookup`
- Purpose: unified inventory (`scope=local|registry|both`).
- Why: first call for any agent to choose context sources.
- Key params: `scope`, `registry`, `packet`, `version`, `include_all_versions`, `tags`, `limit`.
- Return: normalized packet descriptors with `location`, `source_uri`, `digest`, `trust_score`, `installed`.

2. `cpm_query`
- Purpose: single retrieval entrypoint for local + OCI lazy mode.
- Why: avoid decision complexity in the LLM; one tool, many modes.
- Key params: `packet`, `query`, `k`, `registry`, `source_uri`, `indexer`, `reranker`, `embed`.
- Return: full query payload with `compiled_context`, citations, source verification summary, replay id/path.

3. `cpm_resolve_source`
- Purpose: preflight source resolution and trust check without running full query.
- Why: agents can validate provenance before expensive retrieval.
- Key params: `source_uri` or (`registry` + `packet`), `strict_verify` override optional.
- Return: `resolved_uri`, `digest`, `verification.strict_failures`, `trust_score`, `policy_decision`.

### P1 - Agent productivity
4. `cpm_inspect_packet`
- Purpose: inspect schema/manifest/embedding compatibility for a packet.
- Why: prevents bad queries (wrong model/dim/missing index).

5. `cpm_compile_context`
- Purpose: compile structured context (`outline/core_snippets/glossary/risks/citations`) from hits or query response.
- Why: gives LLM immediately consumable context blocks.

6. `cpm_diff_packets`
- Purpose: compare two versions (`drift`, changed sections, risky deltas).
- Why: excellent for release notes and impact analysis tasks.

### P2 - Operations and reliability
7. `cpm_policy_explain`
- Purpose: explain allow/deny/warn decisions for source/token/trust constraints.

8. `cpm_replay_get`
- Purpose: fetch deterministic replay payloads for audit and reproducibility.

## Specific Proposal: Connect `lookup` to registry

### Target behavior
`lookup` should support both local and remote inventory with the same output schema.

Suggested CLI extension (`cpm lookup`):
- `--scope local|registry|both` (default `local` for backward compatibility)
- `--registry <oci://...|registry/repo>`
- `--packet <name[@version]>` (optional filter)
- `--limit <n>`
- existing `--all-versions`, `--format` retained

Suggested MCP extension:
- update MCP `lookup` tool with `scope`, `registry`, `packet`, `limit`
- return merged list with explicit `origin: local|registry`

### Resolution strategy
1. Local branch:
- Keep current `PacketReader`/`LookupCommand` behavior.

2. Registry branch:
- If packet is explicit (`name@version`), resolve via OCI source path and return digest/trust metadata.
- If packet list/search is requested, use Hub endpoint (preferred) when configured.
- If hub unavailable and no explicit packet/version, return actionable error (`registry_listing_not_supported_without_hub`).

3. Shared output schema:
- `name`, `version`, `description`, `tags`, `source_uri`, `digest`, `trust_score`, `installed`, `path`, `origin`.

## Implementation Notes

### Reuse existing CPM primitives
- Source URI resolution: reuse logic equivalent to `QueryCommand._resolve_source_uri`.
- Trust verification: reuse `OciSource.resolve` and trust report fields.
- Policy checks: optionally reuse existing policy evaluation flow for consistency.

### Refactor suggestion (small)
- Extract `_resolve_source_uri` from `QueryCommand` into a shared helper module (e.g. `cpm_core/sources/uri.py`) so `query`, `lookup`, and MCP tools use one canonical resolver.

### MCP server modernization
Current MCP `query` bypasses `QueryCommand` features. Prefer one of:
- Option A: invoke query builtin internally and return structured payload directly.
- Option B: extract reusable query service from `QueryCommand` and call it from both CLI and MCP.

Option B is cleaner long-term and keeps MCP/CLI parity.

## Suggested rollout
1. Milestone 1
- Extend `lookup` CLI + MCP with `scope` and explicit registry packet resolution (`packet@version`).

2. Milestone 2
- Add hub-backed remote listing/search to `lookup`.

3. Milestone 3
- Unify MCP `query` with full CPM query pipeline.

4. Milestone 4
- Add `inspect_packet`, `policy_explain`, `replay_get`, `diff_packets`.

## Success criteria
- LLM can discover packets without local install.
- LLM can run one `cpm_query` tool for both local and registry contexts.
- Same trust/policy semantics across CLI and MCP.
- Deterministic outputs and replay metadata available through MCP.

# MCP Tooling Report (CPM) - Flusso Unificato Aggiornato

Questo report descrive il flusso MCP aggiornato nel repository, con lookup/query remoti, cache hit/miss su `CPM_ROOT`, tool di pianificazione e digest evidenze.

## 1) Tool MCP esposti

Entrypoint: `cpm_plugins/mcp/cpm_mcp_plugin/server.py`

- `lookup`
- `query`
- `plan_from_intent`
- `evidence_digest`

Registrazione tramite `FastMCP`.

## 2) Contratto config runtime

Modulo: `cpm_plugins/mcp/cpm_mcp_plugin/env.py`

Env principali:

- `REGISTRY`
- `CPM_ROOT` (default `.cpm`)
- `EMBEDDING_URL`
- `EMBEDDING_MODEL`

Compatibilità:

- `RAG_CPM_DIR` fallback di `CPM_ROOT`
- `RAG_EMBED_URL` fallback di `EMBEDDING_URL`
- `RAG_EMBED_MODE` fallback del transport mode (`http` default)

Precedenza:

- args tool > env > default (solo `CPM_ROOT` ha default).

## 3) Flusso `lookup` remoto (low-token)

Implementazione: `cpm_plugins/mcp/cpm_mcp_plugin/remote.py::lookup_remote`

Pipeline:

1. Costruisce `source_uri` da `ref` o da `REGISTRY + name + version/alias`.
2. Usa `SourceResolver.lookup_metadata(...)` (`cpm_core/sources/resolver.py`).
3. Path OCI metadata-only:
   - resolve digest
   - fetch manifest
   - fetch blob `packet.manifest.json` (`application/vnd.cpm.packet.manifest.v1+json`)
4. Filtra per `entrypoint`, `kind`, `capability`, `os`, `arch`.
5. Ritorna shortlist deterministica (max 3) con `pinned_uri`.

Cache:

- digest metadata: `CPM_ROOT/cache/metadata/*.json` (core resolver cache)
- alias cache breve: `CPM_ROOT/cache/metadata_alias/*.json` (TTL su `latest` ecc.)

## 4) Flusso `query` lazy (local-hit / remote-miss)

Implementazione: `cpm_plugins/mcp/cpm_mcp_plugin/remote.py::query_remote`

Input tipico:

- `ref` digest-pinned da `lookup` (consigliato)
- `q` testo query

### 4.1 Cache hit

Se `ref` contiene digest e sono presenti:

- `CPM_ROOT/cas/<digest>/payload`
- `CPM_ROOT/index/<digest>/<embedding_fingerprint>/index.faiss`

la query esegue retrieval locale immediato senza fetch remoto.

### 4.2 Cache miss

Su miss:

1. `SourceResolver.resolve_and_fetch(source_uri)` materializza payload.
2. Mirror in `CPM_ROOT/cas/<digest>/payload`.
3. Metadata locale in `CPM_ROOT/meta/<digest>/packet.manifest.json`.
4. Indicizzazione:
   - riuso `faiss/index.faiss` e `vectors.f16.bin` se presenti nel payload
   - altrimenti rebuild da `docs.jsonl` con embedder HTTP (`EMBEDDING_URL`, `EMBEDDING_MODEL`)
5. Cache index in `CPM_ROOT/index/<digest>/<embedding_fingerprint>/`.

Controlli concorrenti:

- lock file `.lock` per evitare rebuild simultanei dello stesso indice.

Output token-min:

- `results[]` con `{score, path, start, end, snippet}`.

## 5) Tool `plan_from_intent`

Implementazione: `remote.py::plan_from_intent`

Strategia:

1. Candidate generation (`name_hint` / `constraints.name` / hint nel testo).
2. Scoring metadata-first (entrypoint/kind/capabilities).
3. Query solo in caso di pareggio.
4. Output piano deterministico:
   - `selected[]` con `pinned_uri`, `entrypoint`, `args_template`, `why`
   - `fallbacks[]`

## 6) Tool `evidence_digest`

Implementazione: `remote.py::evidence_digest`

Pipeline:

1. Invoca `query`.
2. Dedup snippet (`path + snippet`).
3. Trim con budget `max_chars`.
4. Produce:
   - `evidence[]` compresso
   - `summary` tecnico breve.

## 7) Richiamo lazy consigliato

Per integrazioni MCP/LLM:

1. `lookup` remoto per ottenere `pinned_uri`.
2. `query` su `pinned_uri`.
3. opzionale `evidence_digest` per comprimere il contesto.
4. opzionale `plan_from_intent` per orchestrazione tool.

Questo mantiene lookup molto leggero e sposta il costo payload solo quando serve davvero fare query.

## 8) Verifica implementata

Test dedicati:

- `tests/test_mcp_tools_remote.py`
  - lookup remote + alias cache
  - query cache hit (no fetch remoto)
  - query miss con materializzazione + cache index
  - determinismo `plan_from_intent` / `evidence_digest`
  - apply env overrides in `run_server`
- `tests/test_mcp_plugin.py`
  - registrazione comando plugin `mcp:serve`

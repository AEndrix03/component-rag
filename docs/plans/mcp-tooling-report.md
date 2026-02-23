# MCP Tooling Report (CPM) - Stato Attuale

## Obiettivo
Questo report descrive il flusso MCP attuale nel repository, i tool esposti, come viene eseguita una query e come funziona il richiamo lazy verso OCI.

## Perimetro analizzato
- Plugin MCP: `cpm_plugins/mcp/cpm_mcp_plugin/`
- Builtin query: `cpm_core/builtins/query.py`
- Builtin lookup: `cpm_core/builtins/lookup.py`
- Resolver sorgenti OCI: `cpm_core/sources/resolver.py`
- Packaging metadata OCI: `cpm_core/oci/packaging.py`, `cpm_core/oci/packet_metadata.py`

## 1) Come si avvia il flusso MCP

### 1.1 Registrazione plugin
- `cpm_plugins/mcp/plugin.toml`
  - `id = "mcp"`
  - `group = "mcp"`
  - `entrypoint = "cpm_mcp_plugin.entrypoint:MCPEntrypoint"`
- `MCPEntrypoint.init()` carica:
  - `features.MCPServeCommand`
  - `server` (per registrare i tool FastMCP)

### 1.2 Comando di avvio server
- Classe: `MCPServeCommand` in `cpm_plugins/mcp/cpm_mcp_plugin/features.py`
- Comando: `cpm mcp:serve`
- Parametri principali:
  - `--cpm-dir` (default `.cpm`)
  - `--embed-url`
  - `--embeddings-mode` (`http|legacy`)
- `run_server(...)` imposta env (`RAG_CPM_DIR`, `RAG_EMBED_URL`, `RAG_EMBED_MODE`) e avvia `mcp.run()`.

## 2) Tool MCP esposti oggi

File: `cpm_plugins/mcp/cpm_mcp_plugin/server.py`

### 2.1 `lookup` (tool MCP)
- Signature:
  - `lookup(cpm_dir: str | None = None, include_all_versions: bool = False)`
- Implementazione:
  - usa `PacketReader.list_packets(...)`
  - lavora su packet locali installati sotto `.cpm`
- Output:
  - `{ ok, cpm_dir, packets, count }`

### 2.2 `query` (tool MCP)
- Signature:
  - `query(packet: str, query: str, k: int = 5, cpm_dir: str | None = None, embed_url: Optional[str] = None, embed_mode: Optional[str] = None)`
- Implementazione:
  - costruisce `PacketRetriever(...)`
  - legge `manifest.json`, `docs.jsonl`, indice FAISS locale
  - calcola embedding query via `EmbeddingClient`
  - fa nearest-neighbor su FAISS e ritorna top-k
- Output:
  - payload con `ok`, `packet`, `query`, `k`, `embedding`, `results`

Nota: il `query` MCP attuale e` focalizzato su packet locali; non espone direttamente il path lazy OCI del builtin `cpm query`.

## 3) Flusso completo di una query (CLI core)

Entry point: `QueryCommand.run()` in `cpm_core/builtins/query.py`

### 3.1 Pipeline
1. Risolve workspace e carica policy/hub settings.
2. Determina sorgente:
   - `--packet` locale, oppure
   - `--source oci://...`, oppure
   - `--registry ...` (shortcut lazy OCI).
3. Se c'e` una source OCI:
   - policy check locale/remota,
   - `SourceResolver.resolve_and_fetch(source_uri)`,
   - materializzazione in cache locale.
4. Risolve retriever (esplicito, suggerito o default).
5. Risolve trasporto embedding (`--embed-url`, config, fallback).
6. Esegue retrieval (`_invoke_retriever`), opzionale compile context e policy token.
7. Produce output `text` o `json`, e replay log.

## 4) Richiamo query lazy (OCI)

### 4.1 Come viene costruita la source
Metodo: `QueryCommand._resolve_source_uri(...)`
- Accetta:
  - URI esplicita `oci://...`
  - shortcut `--registry` + `--packet`
- Conversioni principali:
  - `oci://repo/name@1.2.3` -> ref OCI valida
  - registry base senza schema + packet -> `oci://<registry>/<packet>`

### 4.2 Come avviene la risoluzione lazy
In `QueryCommand.run()`:
- chiamata a `SourceResolver.resolve_and_fetch(source_uri)`
- `OciSource`:
  - risolve digest remoto
  - verifica trust (strict/non-strict)
  - pull artifact in temp
  - materializza payload in cache CAS locale
- la query poi usa il packet locale materializzato.

### 4.3 Esempi operativi (lazy query)
```bash
cpm query \
  --packet demo@1.0.0 \
  --registry harbor.local/cpm \
  --query "come configuro l'entrypoint?" \
  --format json
```

```bash
cpm query \
  --source oci://harbor.local/cpm/demo:latest \
  --query "quali capability sono supportate?" \
  -k 8
```

```bash
cpm query \
  --source oci://harbor.local/cpm/demo@sha256:... \
  --query "mostrami snippet su autenticazione"
```

## 5) Lookup remoto low-token (manifest + 1 blob metadata)

Builtin: `cpm lookup` in `cpm_core/builtins/lookup.py`

### 5.1 Flusso remoto
1. Risolve `source_uri` (`--source-uri` oppure `--registry + --name + --version/--alias`).
2. `SourceResolver.lookup_metadata(source_uri)`.
3. `OciSource.inspect_metadata(...)`:
   - resolve digest
   - fetch OCI manifest
   - selezione layer metadata `application/vnd.cpm.packet.manifest.v1+json`
   - fetch blob `packet.manifest.json`
   - validazione/normalizzazione metadata
   - cache per digest
4. Applica filtri (`entrypoint`, `kind`, `capability`, `os`, `arch`).
5. Ritorna `pinned_uri` digest-pinned.

### 5.2 Esempio lookup remoto
```bash
cpm lookup \
  --registry harbor.local/cpm \
  --name demo \
  --alias latest \
  --entrypoint query \
  --format json
```

## 6) Relazione tra MCP tools e lazy query

- MCP `lookup` e MCP `query` (plugin FastMCP) sono orientati al workspace locale (`.cpm`).
- Il comportamento lazy OCI completo e` oggi implementato nel builtin `cpm query` e nel builtin `cpm lookup` remoto.
- In pratica:
  - MCP server copre discovery/query locale rapida.
  - CLI core copre pipeline estesa con source OCI lazy, trust/policy e metadata OCI ottimizzato.

## 7) Chiamata "lazy" consigliata in integrazioni MCP

Per client MCP che vogliono modalità lazy OCI oggi:
1. Eseguire `cpm lookup` remoto per ottenere `pinned_uri` e metadata minimale.
2. Eseguire `cpm query --source <pinned_uri> ...` per materializzare on-demand e interrogare.

Questo mantiene lookup leggero (manifest + metadata blob) e posticipa il fetch payload al solo caso di query effettiva.

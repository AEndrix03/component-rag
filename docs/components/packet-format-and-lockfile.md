# Packet Format And Lockfile

Questa pagina documenta il formato output prodotto oggi dal build CPM e la struttura del lockfile.

## Layout Directory Packet

Path packet standard:
- `dist/<packet_name>/<packet_version>/`

Contenuto tipico:
1. `cpm.yml`
2. `docs.jsonl`
3. `manifest.json`
4. `vectors.f16.bin` (se embedding ok)
5. `faiss/index.faiss` (se embedding ok)
6. `<lockfile_name>` (default `cpm.lock.json`, gestito da `cpm build`)
7. archivio opzionale sibling: `.../<version>.tar.gz` o `.../<version>.zip`

## `docs.jsonl`

Un record JSON per riga, scritto da `write_docs_jsonl`.

Campi per entry:
- `id`: id chunk (`<rel_path>:<counter>`),
- `text`: testo chunk,
- `hash`: SHA-256 del testo chunk,
- `metadata`: dizionario chunk metadata (`path`, `ext`, eventuali campi custom).

Esempio:

```json
{"id":"src/app.py:42","text":"def main(): ...","hash":"4f1d...","metadata":{"path":"src/app.py","ext":".py"}}
```

## `vectors.f16.bin`

Matrice embedding row-major `float16`:
- shape logica: `(num_chunks, embedding_dim)`,
- ordine righe allineato all'ordine dei chunk in `docs.jsonl`.

Il file viene generato da `write_vectors_f16`.

## `faiss/index.faiss`

Indice FAISS `IndexFlatIP` su vettori normalizzati.

Con vettori L2-normalizzati, inner product equivale a similarita` coseno.

## `cpm.yml`

Metadata YAML semplice (key-value flat), scritto da `_write_cpm_yml`.

Campi attuali:
- `cpm_schema`,
- `name`,
- `version`,
- `description`,
- `tags` (CSV),
- `entrypoints` (CSV),
- `embedding_model`,
- `embedding_dim`,
- `embedding_normalized`,
- `created_at` (UTC ISO-8601).

Esempio:

```yaml
cpm_schema: 1
name: my-docs
version: 1.0.0
description: docs repository
tags: docs,python
entrypoints: query
embedding_model: sentence-transformers/all-MiniLM-L6-v2
embedding_dim: 384
embedding_normalized: true
created_at: 2026-02-22T12:00:00Z
```

## `manifest.json`

Serializzazione `PacketManifest`.

Sezioni principali:
1. `schema_version`
2. `packet_id`
3. `embedding`
4. `similarity`
5. `files`
6. `counts`
7. `source`
8. `cpm`
9. `incremental`
10. `checksums`
11. campi extra liberi (`extras`, mergeati top-level)

### `embedding`

Esempio:

```json
{
  "provider": "sentence-transformers",
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "dim": 384,
  "dtype": "float16",
  "normalized": true,
  "max_seq_length": 1024
}
```

### `files`

Success case:

```json
{
  "docs": "docs.jsonl",
  "vectors": {"path":"vectors.f16.bin","format":"f16_rowmajor"},
  "index": {"path":"faiss/index.faiss","format":"faiss"},
  "calibration": null
}
```

Embedding failure case:

```json
{
  "docs": "docs.jsonl",
  "vectors": null,
  "index": null,
  "calibration": null
}
```

### `checksums`

Mappa per file relativo:
- `algo` (attualmente `sha256`),
- `value` (digest hex).

Vengono inclusi solo file esistenti tra target previsti.

## Lockfile (`cpm.lock.json`)

Generato con `render_lock(...)`, scritto con `write_lock(...)`.

Struttura:
1. `lockfileVersion`
2. `packet`
3. `inputs`
4. `pipeline`
5. `models`
6. `artifacts`
7. `resolution`

### `packet`

Campi:
- `name`,
- `version`,
- `packet_id`,
- `resolved_packet_id`,
- `build_profile`.

`resolved_packet_id` e` hash deterministico su:
- name/version,
- build profile,
- path sorgente normalizzato,
- config hash.

### `inputs`

Fingerprint della sorgente (`_hash_inputs`):
- hash albero directory,
- hash file per input rilevanti.

### `pipeline`

Step attuali:
1. `build`,
2. `embed`,
3. `index`.

Ogni step include:
- `plugin`,
- `plugin_version`,
- `config_hash`,
- `params`.

### `models`

Descrive modello embedding risolto:
- provider,
- model,
- revision,
- dtype,
- device_policy,
- normalize,
- max_seq_length.

### `artifacts`

Hash file output principali (`artifact_hashes`):
- `chunks_manifest_hash` -> `docs.jsonl`,
- `embeddings_hash` -> `vectors.f16.bin` (se presente),
- `index_hash` -> `faiss/index.faiss` (se presente),
- `packet_manifest_hash` -> `manifest.json`.

### `resolution`

Metadata risoluzione lock:
- `generated_at`,
- `cpm_version`,
- `warnings`.

## Verifica Lock e Artifact

`cpm build verify` controlla:
1. lockfile version,
2. match completo `packet/inputs/pipeline/models` rispetto al plan corrente,
3. hash artifact presenti.

Con `--frozen-lockfile` viene inoltre rifiutato lock con sezioni non deterministiche (`non_deterministic=true` in pipeline/models).

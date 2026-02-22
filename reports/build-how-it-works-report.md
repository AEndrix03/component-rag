# CPM Build: funzionamento completo e formato prodotto (stato attuale)

## 1. Scopo

Questo report descrive in modo operativo come funziona oggi il comando `cpm build` e quali artifact produce, sulla base dell'implementazione attuale nel codice.

Riferimenti principali:
- `cpm_core/builtins/build.py`
- `cpm_core/build/builder.py`
- `cpm_core/packet/io.py`
- `cpm_core/packet/models.py`
- `cpm_core/packet/lockfile.py`

## 2. Entry point e comandi disponibili

La feature CLI `cpm:build` e` implementata da `BuildCommand` (`cpm_core/builtins/build.py`).

Subcommand supportati:
1. `run` (default)
2. `embed`
3. `lock`
4. `verify`
5. `describe`
6. `inspect`

Opzioni principali:
- `--workspace-dir`
- `--config`
- `--builder`
- `--source`
- `--destination`
- `--name`
- `--packet-version` / `--version`
- `--description`
- `--model`
- `--max-seq-length`
- `--lines-per-chunk`
- `--overlap-lines`
- `--archive-format` (`tar.gz` | `zip`)
- `--no-archive`
- `--embed-url`
- `--embeddings-mode`
- `--timeout`
- `--input-size`
- `--lockfile`
- `--frozen-lockfile`
- `--update-lock`

## 3. Risoluzione configurazione (merge)

La risoluzione input e` gestita da `_merge_invocation(...)`.

Ordine di priorita`:
1. argomenti CLI
2. `config/build.toml` (o path passato con `--config`)
3. default `DefaultBuilderConfig`
4. fallback env/embedding provider (per campi embedding)

Campi risolti:
- source directory
- destination root
- packet name/version/description
- chunking (`lines_per_chunk`, `overlap_lines`)
- embedding (`model_name`, `max_seq_length`, `embed_url`, `embeddings_mode`, `timeout`, `input_size`)
- archivio (`archive`, `archive_format`)
- builder name

Path packet target:
- `<destination_root>/<packet_name>/<packet_version>`

## 4. Risoluzione builder

`--builder` (default `cpm:default-builder`) viene risolto nel feature registry.

Se non trovato:
- errore + hint builder disponibili.

Se trovato:
- viene anche determinata la `builder_plugin_version` da usare nel lock plan.

## 5. Lock plan (sempre prima del build)

Viene costruito un piano (`build_resolved_plan`) con:
- `packet` (name/version/packet_id/resolved_packet_id/build_profile)
- `inputs` (fingerprint sorgente)
- `pipeline` (`build`, `embed`, `index`)
- `models` (metadata modello embedding)

Questo piano serve per:
- creare lockfile coerenti
- verificare lockfile esistenti

## 6. Flusso `cpm build run` (default)

Sequenza:
1. valida `name` e `version`
2. crea directory output
3. risolve builder
4. costruisce lock plan
5. gestisce lockfile:
   - se esiste e `--update-lock` non c'e`: verifica coerenza
   - con `--frozen-lockfile`: richiede lock esistente e deterministico
6. esegue builder (`_execute_builder`)
7. aggiorna lockfile finale con hash artifact reali

Se builder = `DefaultBuilder`:
- chiamata diretta a `DefaultBuilder.build(source, destination=packet_dir)`.

Se builder custom:
- inietta argomenti risolti su `argv`
- usa `run(argv)` se disponibile, altrimenti `build(...)`

## 7. Flusso `cpm build embed`

Scopo: rigenerare embeddings/index da un packet gia` chunkato.

Prerequisito:
- `docs.jsonl` presente nel packet dir (`--source`).

Sequenza:
1. legge chunk da `docs.jsonl`
2. recupera metadata da `manifest.json` (se esiste)
3. determina `name/version/description` (con eventuali override CLI)
4. richiama `materialize_packet(...)` con `incremental_enabled=False`
5. aggiorna lockfile hash artifact se lock presente o `--update-lock`

## 8. Flusso `cpm build lock`

Genera lockfile senza eseguire build:
1. calcola plan
2. calcola hash artifact gia` presenti
3. scrive lockfile

## 9. Flusso `cpm build verify`

Controlli:
1. lockfile coerente con plan corrente (`packet`, `inputs`, `pipeline`, `models`)
2. hash artifact coerenti (`artifacts`)
3. con `--frozen-lockfile`: nessuna sezione `non_deterministic` in `pipeline/models`

Esito:
- `0` se tutto ok
- `1` con messaggi mismatch in caso contrario

## 10. Flussi utility

`describe`:
- aggiorna `description` in `cpm.yml` e `manifest.json`.

`inspect`:
- stampa path packet risolto e flag `exists`.

## 11. Builder di default: pipeline interna

`DefaultBuilder.build(...)`:
1. valida source
2. scandisce sorgenti (`_scan_source`)
3. chunking per linee (`_chunk_text`)
4. chiama `materialize_packet(...)`

### 11.1 Scan e chunking

`_scan_source`:
- visita ricorsiva file
- include solo estensioni supportate (`CODE_EXTS | TEXT_EXTS`)
- per ogni file non vuoto crea chunk `DocChunk` con:
  - `id = <rel_path>:<counter_globale>`
  - `metadata.path`
  - `metadata.ext`

`_chunk_text`:
- chunk basati su numero linee
- overlap configurabile
- scarta chunk vuoti

### 11.2 Materializzazione packet (`materialize_packet`)

Passi principali:
1. scrive `docs.jsonl`
2. carica cache incrementale se compatibile (manifest+docs+vectors, stesso model/max_seq_length)
3. decide chunk da riusare vs ri-embeddare (via hash chunk)
4. invoca embedding server per i chunk mancanti
5. compone matrice finale vettori
6. salva FAISS (`faiss/index.faiss`)
7. salva vettori (`vectors.f16.bin`)
8. scrive `cpm.yml`
9. scrive `manifest.json` + checksums
10. crea archivio opzionale (`tar.gz`/`zip`)

### 11.3 Comportamento in errore embedding

Se embedding health/check o richiesta embedding fallisce:
- `docs.jsonl` viene comunque scritto
- viene scritto metadata parziale (`cpm.yml`, `manifest.json` con `dim=0`, `vectors/index=null`, extras di errore)
- `materialize_packet` ritorna `None`
- il comando build termina con errore

## 12. Formato output prodotto

Directory tipica:

```text
dist/<name>/<version>/
  cpm.yml
  docs.jsonl
  manifest.json
  vectors.f16.bin          # se embedding ok
  faiss/
    index.faiss            # se embedding ok
  cpm.lock.json            # nome default lockfile
```

Archivio opzionale:
- `dist/<name>/<version>.tar.gz` oppure `.zip`

### 12.1 `docs.jsonl`

Un JSON per riga:
- `id`
- `text`
- `hash` (sha256 del text)
- `metadata`

Esempio:

```json
{"id":"src/app.py:1","text":"...","hash":"...","metadata":{"path":"src/app.py","ext":".py"}}
```

### 12.2 `vectors.f16.bin`

Matrice float16 row-major:
- shape logica `(num_chunks, embedding_dim)`
- ordine allineato alle righe di `docs.jsonl`

### 12.3 `faiss/index.faiss`

Indice `faiss.IndexFlatIP` su vettori normalizzati (coseno via inner product).

### 12.4 `cpm.yml`

Chiavi flat:
- `cpm_schema`
- `name`
- `version`
- `description`
- `tags`
- `entrypoints`
- `embedding_model`
- `embedding_dim`
- `embedding_normalized`
- `created_at`

### 12.5 `manifest.json`

Struttura:
- `schema_version`
- `packet_id`
- `embedding`
- `similarity`
- `files`
- `counts`
- `source`
- `cpm`
- `incremental`
- `checksums`
- campi extra top-level (`extras` mergeati)

Campi notevoli:
- `files.docs = "docs.jsonl"`
- `files.vectors` e `files.index` valorizzati solo se embedding riuscito
- `checksums` contiene hash sha256 dei file presenti

## 13. Lockfile (`cpm.lock.json`)

Struttura:
1. `lockfileVersion`
2. `packet`
3. `inputs`
4. `pipeline`
5. `models`
6. `artifacts`
7. `resolution`

`artifacts` (quando disponibili):
- `chunks_manifest_hash` -> `docs.jsonl`
- `embeddings_hash` -> `vectors.f16.bin`
- `index_hash` -> `faiss/index.faiss`
- `packet_manifest_hash` -> `manifest.json`

`resolution`:
- `generated_at`
- `cpm_version`
- `warnings`

## 14. Exit codes e failure modes principali

`0`:
- successo comando/subcommand.

`1`:
- source/packet dir mancante
- builder non trovato
- lockfile invalido o incoerente senza `--update-lock`
- lock richiesto frozen ma mancante/non deterministico
- errore embedding server/request
- manifest/lock non parseabile

## 15. Comandi esemplificativi

Build completo:

```bash
cpm build run \
  --source ./docs \
  --destination ./dist \
  --name my-docs \
  --version 1.0.0 \
  --lockfile cpm.lock.json
```

Solo lock:

```bash
cpm build lock --source ./docs --destination ./dist --name my-docs --version 1.0.0
```

Verify:

```bash
cpm build verify --source ./docs --destination ./dist --name my-docs --version 1.0.0 --frozen-lockfile
```

Re-embed da packet esistente:

```bash
cpm build embed --source ./dist/my-docs/1.0.0 --model sentence-transformers/all-MiniLM-L6-v2
```

## 16. Conclusione

Il build attuale combina in un unico comando:
- preparazione dati (`scan + chunk`),
- embedding/indexing,
- metadata packet,
- lock e verificabilita` artifact.

Il formato prodotto e` pensato per query locale veloce e per verifiche di coerenza/riproducibilita` tramite lockfile.

# Chunking And Builders

Questa pagina descrive come il builder di default (`cpm:default-builder`) trasforma una sorgente locale in un packet CPM.

## Builder Registrati

Il runtime registra il builder built-in `cpm:default-builder`.

Se viene specificato `--builder` con un builder plugin/custom:
- il comando `cpm build` risolve la feature nel registry,
- passa i parametri risolti al builder (`run(argv)` oppure `build(...)`).

## Builder Di Default: Fasi

Il builder di default (`DefaultBuilder`) esegue:
1. scan file sorgente (`_scan_source`),
2. chunking testuale per linee (`_chunk_text`),
3. scrittura `docs.jsonl`,
4. embedding incrementale (cache-aware),
5. costruzione indice FAISS (`IndexFlatIP`),
6. serializzazione metadata (`cpm.yml`, `manifest.json`, checksums),
7. archivio opzionale (`tar.gz` o `zip`).

## Scan Sorgenti

`_scan_source(...)` attraversa ricorsivamente `source` e include solo estensioni supportate (`CODE_EXTS` + `TEXT_EXTS`).

Per ogni file indicizzato:
- legge testo UTF-8 con fallback permissivo,
- scarta file vuoti,
- calcola path relativo POSIX,
- incrementa `ext_counts`,
- produce chunk `DocChunk`.

Metadata chunk per file:
- `metadata.path`: path relativo file,
- `metadata.ext`: estensione lowercase.

Formato id chunk:
- `<relative_path>:<chunk_counter_progressivo_globale>`.

## Chunking

`_chunk_text(text, lines_per_chunk, overlap_lines)`:
- segmenta per linee,
- usa finestra scorrevole con overlap,
- produce blocchi non vuoti con join `\n`.

Regole:
- `lines_per_chunk <= 0` => chunk unico (tutte le linee),
- `overlap_lines` clampato tra `0` e `lines_per_chunk - 1`,
- step = `lines_per_chunk - overlap`.

## Embedding e Cache Incrementale

Nel percorso `build run`, `incremental_enabled=True`.

La cache viene caricata solo se sono presenti:
- `manifest.json`,
- `docs.jsonl`,
- `vectors.f16.bin`,
- con compatibilita` modello (`embedding.model`) e `max_seq_length`.

La cache usa `hash` chunk (da `docs.jsonl`) come chiave:
- chunk invariati => vettori riusati,
- chunk nuovi => embedding remoto,
- chunk rimossi => conteggiati in `incremental.removed`.

Se dimensione embedding cambia rispetto alla cache:
- cache invalidata,
- re-embedding completo.

## Fault Tolerance Embedding

Se embedding server non e` raggiungibile o embedding fallisce:
- viene comunque scritto `docs.jsonl`,
- viene scritto `cpm.yml` con `embedding_dim: 0`,
- viene scritto `manifest.json` parziale con:
1. `files.vectors = null`,
2. `files.index = null`,
3. `extras.build_status = "embedding_failed"`,
4. `extras.build_error = <reason>`.

In questo scenario `materialize_packet(...)` ritorna `None` e `cpm build` fallisce.

## Output Builder

In caso successo pieno:
- `docs.jsonl`,
- `vectors.f16.bin`,
- `faiss/index.faiss`,
- `cpm.yml`,
- `manifest.json`,
- archivio opzionale (`<packet_dir>.tar.gz` o `<packet_dir>.zip`).

## Parametri Principali Builder

`DefaultBuilderConfig`:
- `model_name`,
- `max_seq_length`,
- `lines_per_chunk`,
- `overlap_lines`,
- `version`,
- `packet_name`,
- `description`,
- `archive`,
- `archive_format`,
- `embed_url`,
- `embeddings_mode`,
- `timeout`,
- `input_size`.

## Note Per Builder Custom

Per integrazione corretta con lock/verify conviene:
1. mantenere output compatibile (`docs.jsonl`, `manifest.json`, eventuali vettori/index),
2. rispettare destination passato da `cpm build`,
3. mantenere naming `name/version` coerente con invocation.

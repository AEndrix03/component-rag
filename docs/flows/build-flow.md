# Build Flow

Questa pagina descrive il comportamento attuale del comando `cpm build` (runtime `cpm_core`), inclusi:
- risoluzione config/argomenti,
- selezione builder,
- fasi `run`, `embed`, `lock`, `verify`, `describe`, `inspect`,
- lockfile e controlli di coerenza.

## Entry Point

Il comando utente `cpm build ...` risolve la feature `cpm:build` (`BuildCommand`) e usa parser/subcommand definiti in `cpm_core/builtins/build.py`.

`BuildCommand.configure(...)` espone:
- opzioni comuni di run (`--source`, `--destination`, `--name`, `--packet-version|--version`, `--model`, `--embed-url`, `--lockfile`, `--frozen-lockfile`, `--update-lock`, ecc.),
- subcommand:
1. `run` (default),
2. `embed`,
3. `lock`,
4. `verify`,
5. `describe`,
6. `inspect`.

## Risoluzione Workspace e Config

Prima di ogni operazione:
1. viene risolto/inizializzato il workspace (`_WorkspaceAwareCommand._resolve`),
2. viene costruita una `_BuildInvocation` con `_merge_invocation(...)`.

Ordine di precedenza dei valori:
1. CLI args,
2. `config/build.toml` (o `--config` esplicito),
3. fallback default (`DefaultBuilderConfig`),
4. per alcuni campi embeddings anche variabili ambiente (`RAG_EMBED_URL`, `RAG_EMBED_MODE`) e provider embeddings di workspace.

Campi principali risolti:
- `source` (default `.`),
- `destination_root` (default `./dist`),
- `packet_name`,
- `packet_version`,
- `description`,
- parametri chunking (`lines_per_chunk`, `overlap_lines`),
- parametri embedding (`model_name`, `max_seq_length`, `embed_url`, `embeddings_mode`, `timeout`, `input_size`),
- opzioni archivio (`archive`, `archive_format`).

Path packet target:
- `${destination_root}/${packet_name}/${packet_version}`.

## Risoluzione Builder

`--builder` (default `cpm:default-builder`) viene risolto via feature registry (`_resolve_builder_entry`).

Se il builder non esiste:
- errore con hint dei builder disponibili.

Se il builder e` risolto:
- si determina anche la versione plugin builder per il lock plan (`_resolve_builder_plugin_version`).

## Lock Plan (pre-build)

Prima del build viene sempre calcolato un piano deterministico (`build_resolved_plan`) con:
- hash configurazione risolta (`config_hash`),
- fingerprint input source (`inputs`),
- pipeline steps (`build`, `embed`, `index`),
- metadata modello embeddings,
- `resolved_packet_id`.

Questo piano alimenta lock/verify.

## Flusso `cpm build run` (default)

Sequenza operativa:
1. valida `--name` e `--version`,
2. crea directory output (`destination_root` e `packet_dir`),
3. carica lockfile se presente (`<packet_dir>/<lockfile_name>`),
4. valida lock corrente contro piano se `--update-lock` non e` attivo,
5. blocca se `--frozen-lockfile` e` attivo e lock mancante/non deterministico,
6. se necessario rigenera lock preliminare,
7. esegue builder (`_execute_builder`),
8. ricalcola hash artifact e riscrive lockfile finale.

### Esecuzione Builder

Caso default builder (`DefaultBuilder`):
- istanzia `DefaultBuilder(config=invocation.config)`,
- invoca `build(source, destination=packet_dir)`.

Caso builder custom:
- istanzia builder,
- inietta in `argv` i campi risolti (`source`, `destination`, `name`, `packet_version`, ecc.),
- se esiste `run(argv)` usa quello,
- altrimenti fallback su `build(source, destination=...)`.

## Flusso `cpm build embed`

`embed` e` pensato per packet gia` materializzati con `docs.jsonl` presente:
1. valida `--source` come packet dir,
2. legge chunk da `docs.jsonl`,
3. recupera metadata esistenti da `manifest.json` (se presente),
4. riesegue materializzazione embedding/index (senza scan sorgenti),
5. aggiorna lockfile hash artifact se lock presente o `--update-lock`.

Note:
- in `embed` la incremental cache e` disabilitata (`incremental_enabled=False`),
- consente override `--name`, `--version`, `--description`.

## Flusso `cpm build lock`

Genera/aggiorna lockfile senza eseguire build:
1. costruisce lock plan,
2. calcola hash artifact gia` presenti in packet dir,
3. scrive lockfile (`render_lock` + `write_lock`).

## Flusso `cpm build verify`

Verifica:
1. coerenza lockfile vs piano corrente (`verify_lock_against_plan`),
2. integrita` artifact (`verify_artifacts`),
3. se `--frozen-lockfile`, rifiuta sezioni non deterministiche (`non_deterministic` in pipeline/models).

Output:
- `verify ok` oppure lista mismatch esplicita.

## Flussi Utility

`describe`:
- aggiorna `description` in `cpm.yml` e `manifest.json` del packet target.

`inspect`:
- stampa path risolto packet dir e `exists=true/false`.

## Error Handling Principale

Il comando ritorna `1` in questi casi (non esaustivo):
- source o packet directory mancante,
- builder non risolto,
- lockfile invalido o incoerente senza `--update-lock`,
- lock richiesto frozen ma mancante/non deterministico,
- embedding server non raggiungibile,
- errore durante embedding request.

## Esempio Minimo

```bash
cpm build run \
  --source ./docs \
  --destination ./dist \
  --name my-docs \
  --version 1.0.0 \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --lockfile cpm.lock.json
```

Output atteso:
- `./dist/my-docs/1.0.0/` con artifact packet,
- lockfile in packet dir,
- opzionalmente archivio `.tar.gz` o `.zip` affiancato alla directory packet.

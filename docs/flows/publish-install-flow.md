# Publish Install Flow

## Obiettivo
Distribuire packet versionati via registry OCI e reinstallarli in workspace diversi in modo riproducibile.

## Passi
1. Build packet locale (`cpm build ...`).
2. Publish (`cpm publish --from-dir <packet_dir> ...`).
3. Install (`cpm install <name>@<version> ...`).
4. Activate con package manager (`cpm pkg use ...`).

## Fallback publish
- `--from-dir` puo puntare direttamente alla directory packet (`dist/<name>/<version>`).
- Se `--from-dir` non esiste, CPM prova fallback a `dist/<name>/<version>` quando esiste una sola versione.
- `--registry` accetta repository OCI (`registry.local/project`) e URL `http(s)://host[:port][/path]`, normalizzato in ref OCI.
- Errori OCI (es. `oras` mancante) vengono riportati come errore controllato senza traceback.

## Variante no-embed
- publish con `--no-embed` per pacchetti leggeri,
- install puo mantenere no-embed oppure selezionare modello/provider compatibile.

## Tracciabilita
Digest OCI + install lock permettono audit e rollback controllato.

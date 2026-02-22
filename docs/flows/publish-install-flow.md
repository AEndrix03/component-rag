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
- `--registry` accetta solo riferimenti OCI (`oci://...` o `registry.local/project`).
- Errori OCI (es. `oras` mancante) vengono riportati come errore controllato senza traceback.

## Variante no-embed
- publish con `--no-embed` (legacy) o `--no-embeddings` per pacchetti leggeri.
- modalita `--minimal` per payload minimo (no docs, no embeddings).
- toggle espliciti `--with-docs/--no-docs` e `--with-embeddings/--no-embeddings`.
- install puo mantenere no-embed oppure selezionare modello/provider compatibile.

## Lookup remoto
- `cpm lookup --source-uri oci://...` usa percorso low-token:
  1. fetch manifest OCI
  2. fetch blob metadata (`packet.manifest.json`)
- il payload non viene scaricato per il solo lookup.

## Tracciabilita
Digest OCI + install lock permettono audit e rollback controllato.

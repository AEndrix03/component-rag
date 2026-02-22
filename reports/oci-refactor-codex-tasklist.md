# OCI Refactor Plan - Codex-Ready Task List

Questo documento traduce il piano in una sequenza esecutiva pronta per Codex, con slicing per PR, task verificabili, uso esplicito di SerenaMCP e policy docs/commit.

## Obiettivi non negoziabili

- Lookup MCP in massimo 2 fetch: `manifest` + blob metadata (`packet.manifest.json`).
- Publish sempre con metadata layer stabile/versionato.
- Payload pesanti opzionali e separabili (`docs`, `embeddings`).
- Output deterministico, digest-based, cache-friendly.
- Compatibilità backward con percorso di migrazione chiaro.

## Convenzioni operative

- Analisi e navigazione: SerenaMCP (`find_file`, `search_for_pattern`, `get_symbols_overview`, `find_symbol`).
- Edit preferenziale: SerenaMCP per modifiche simboliche; patch mirata per file docs nuovi.
- Ogni PR include:
  - test o aggiornamento test
  - aggiornamento docs in `docs/`
  - nota compatibilità se tocca interfacce/CLI/mediaType
- Commit atomici con conventional commits.

---

## PR-0: Baseline e invarianti

### Scope

Mappare stato attuale build/publish OCI e fissare test golden minimi.

### Task Codex (SerenaMCP)

1. Mappare entrypoint build/publish:
   - `cpm_core/builtins/build.py`
   - `cpm_core/builtins/publish.py`
   - `cpm_core/oci/packaging.py`
   - `cpm_core/oci/client.py`
2. Inventariare media type e layer prodotti oggi.
3. Aggiungere test golden:
   - publish packet minimale -> snapshot manifest OCI
   - verifica lookup metadata senza fetch payload pesante
4. Scrivere docs baseline:
   - `docs/oci/overview.md` (as-is, problemi, target-state).

### Exit criteria

- Matrice as-is completata (file/layer/mediaType/size tipiche).
- Test golden presenti e verdi.

### Commit

- `chore(oci): baseline inventory + golden tests scaffold`

---

## PR-1: Schema Packet Metadata v1

### Scope

Definire contratto stabile e minimalista per `packet.manifest.json`.

### Task Codex (SerenaMCP)

1. Creare `schemas/packet-metadata/v1.json` con campi:
   - `schema`, `schema_version`
   - `packet` (`name`, `version`, `description?`, `tags?`, `kind?`, `entrypoints?`, `capabilities?`)
   - `compat` (`os?`, `arch?`, `cpm_min_version?`)
   - `links?`
   - `payload.files[]` (`name`, `digest?`, `size?`) e `payload.full_ref?`
   - `source` (`manifest_digest?`, `created_at?`, `build?`)
2. Aggiornare serializer/generator metadata in modo deterministico:
   - ordine campi stabile
   - assenza di contenuti voluminosi non necessari
3. Documentare:
   - `docs/oci/packet-metadata.md` con esempi validi.

### Exit criteria

- Schema v1 versionato.
- Output metadata identico su run ripetute a parità input.

### Commit

- `feat(oci): define packet metadata schema v1`

---

## PR-2: Metadata layer OCI stabile e piccolo

### Scope

Garantire lookup affidabile con `manifest + 1 blob`.

### Task Codex (SerenaMCP)

1. Nel publish OCI:
   - sempre presente layer `application/vnd.cpm.packet.manifest.v1+json`
   - dimensione metadata contenuta (niente source manifest completo di default)
   - opzionale: layer metadata in prima posizione
2. Inserire fallback debug solo dietro flag esplicito per payload diagnostico.
3. Aggiungere test:
   - parse manifest -> identificazione metadata layer
   - fetch blob metadata -> validazione contro `schemas/packet-metadata/v1.json`
4. Aggiornare docs:
   - `docs/cli/publish.md`
   - `docs/oci/overview.md`

### Exit criteria

- Resolver può completare lookup con 2 fetch.
- Schema validation metadata green.

### Commit

- `refactor(publish): make packet metadata layer stable and small`
- `test(oci): validate metadata layer schema`

---

## PR-3A: Modalità publish minimal

### Scope

Aggiungere `--minimal` per artefatti ridotti e lookup-first.

### Task Codex (SerenaMCP)

1. Implementare `cpm publish --minimal`:
   - include metadata + `cpm.yml` + `manifest.json` minimo
   - esclude `docs.jsonl`, embeddings e indici
2. Test dedicati e snapshot manifest OCI modalità minimal.
3. Aggiornare docs:
   - `docs/cli/publish.md` con esempi.

### Exit criteria

- Manifest minimal deterministico.
- Install/resolve da minimal validi (nei limiti attesi).

### Commit

- `feat(cli): add publish --minimal mode`

---

## PR-3B: Toggle espliciti docs/embeddings

### Scope

Controllo fine del payload publish full.

### Task Codex (SerenaMCP)

1. Esporre flag:
   - `--with-docs` / `--no-docs`
   - `--with-embeddings` / `--no-embeddings`
   - mantenere compat con `--no-embed` (se legacy)
2. Popolare `payload.files[]` nel metadata con digest/size per integrità.
3. Aggiornare test per combinazioni principali.
4. Aggiornare docs flags e tabella compatibilità.

### Exit criteria

- Combinazioni flag rispettate.
- Metadata riflette sempre il payload realmente pubblicato.

### Commit

- `feat(cli): explicit payload toggles for docs/embeddings`

---

## PR-4A: Resolver low-token (manifest + metadata)

### Scope

Lookup orientato a latenza/costo minimo.

### Task Codex (SerenaMCP)

1. Implementare resolver (`cpm lookup` o libreria dedicata):
   - input: `name`, `version?`, `constraints?`
   - resolve ref/alias (`latest`, `stable`, `major`)
   - fetch manifest
   - fetch metadata blob
   - validate schema + filtri + ranking
   - output: ref digest pinned + entrypoint selezionato
2. Test:
   - matching entrypoint/capabilities
   - fallback alias
   - compat os/arch
3. Docs:
   - `docs/mcp/lookup.md`

### Exit criteria

- Nessun download payload pesante durante lookup.
- Output resolver digest-pinned consistente.

### Commit

- `feat(lookup): resolve packets via oci manifest + metadata blob`

---

## PR-4B: Cache digest-based

### Scope

Ridurre fetch ripetuti.

### Task Codex (SerenaMCP)

1. Implementare cache locale per digest:
   - chiavi: `manifestDigest`, `metadataDigest` (e config digest se utile)
2. Integrazione nel resolver con invalidazione naturale digest-based.
3. Test cache-hit/cache-miss.
4. Docs caching behavior.

### Exit criteria

- Lookup ripetuti senza refetch non necessario.

### Commit

- `feat(lookup): add digest cache`

---

## PR-5: Catalog opzionale per ricerca ampia

### Scope

Supporto ricerca su dataset grande senza registry search API.

### Task Codex (SerenaMCP)

1. Definire `cpm-catalog.jsonl` (1 riga = 1 versione packet).
2. Implementare `cpm catalog build`:
   - sorgenti: seed list configurata o workspace locale
   - publish catalog in ref nota (`cpm/catalog:latest`)
3. Estendere lookup con `--use-catalog`.
4. Docs:
   - `docs/oci/catalog.md`

### Exit criteria

- Ricerca filtrata da singolo blob catalog + resolve digest del match.

### Commit

- `feat(catalog): publish downloadable catalog for fast search`

---

## PR-6: Hardening compatibilità OCI e backward compat

### Scope

Evitare rotture con registry eterogenei e metadata legacy.

### Task Codex (SerenaMCP)

1. Compat layer media type/alias per periodo transitorio.
2. Fallback:
   - se metadata v1 assente -> tentare legacy (`cpm.yml`), altrimenti errore chiaro.
3. Test compat:
   - accept header OCI/Docker
   - HEAD/GET blob
   - fixture/mock registry behavior
4. Docs:
   - `docs/oci/compat.md`

### Exit criteria

- Resolver robusto su registries comuni e pacchetti legacy.

### Commit

- `refactor(oci): backward compatible metadata resolution + registry compatibility tests`

---

## PR-7A: Refactor interno moduli

### Scope

Separare responsabilità e ridurre duplicazioni.

### Task Codex (SerenaMCP)

1. Estrarre/modularizzare:
   - `oci_client`
   - `packet_metadata`
   - `publish_plan`
2. Aggiornare wiring chiamanti.
3. Test regressione.

### Exit criteria

- Moduli coesi, dipendenze pulite, nessuna regressione funzionale.

### Commit

- `refactor(core): split oci client, metadata, publish plan`

---

## PR-7B: Deprecazioni e migrazione

### Scope

Chiusura ciclo con warning, date e guide migrazione.

### Task Codex (SerenaMCP)

1. Introdurre warning deprecazione per flag/percorsi legacy.
2. Definire finestra di rimozione.
3. Aggiornare:
   - changelog
   - note migrazione docs

### Exit criteria

- Utenti legacy guidati, nessun breaking improvviso.

### Commit

- `docs: add migration notes for publish/lookup`

---

## DoD globale

- `packet.manifest.json` sempre fetchabile/validabile schema v1 via manifest OCI.
- Lookup operativo con 2 fetch (`manifest` + `metadata blob`).
- `publish --minimal` disponibile e testato.
- Cache digest-based efficace.
- Docs complete: overview, schema, publish flags, lookup, compat/migration.
- Golden tests bloccano regressioni su mediaType e ordine/forma metadata.

## Sequenza consigliata di esecuzione

1. PR-0
2. PR-1
3. PR-2
4. PR-3A
5. PR-3B
6. PR-4A
7. PR-4B
8. PR-5
9. PR-6
10. PR-7A
11. PR-7B

## Nota implementativa

La priorità di valore è: PR-0 -> PR-2 -> PR-3A -> PR-4A. Questo blocco da solo abilita già lookup low-token e publish coerente OCI per il caso principale.

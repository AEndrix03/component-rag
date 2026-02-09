# OCI / Install / Embed Discovery Recon

## Runtime Hooks Reali
- CLI dispatcher principale: `cpm_cli/main.py` (`main`, `_extract_command_spec`, registry dispatch).
- Comandi builtin registrati in: `cpm_core/builtins/__init__.py`.
- Build command reale: `cpm_core/builtins/build.py`.
- Query command reale: `cpm_core/builtins/query.py`.
- Gestione pacchetti locali: `cpm_core/builtins/pkg.py`, `cpm_builtin/packages/manager.py`.
- Loader config embeddings: `cpm_builtin/embeddings/config.py` (`EmbeddingsConfigService`, `EmbeddingProviderConfig`).
- Transport embedding HTTP/OpenAI: `cpm_builtin/embeddings/connector.py`, `cpm_builtin/embeddings/openai.py`, `cpm_builtin/embeddings/client.py`.

## Lacune Tecniche
- `cpm install` e `cpm publish` OCI non esistono nel runtime attuale.
- Layer registry core è placeholder: `cpm_core/registry/client.py`.
- Nessun client OCI standard (resolve/push/pull) nel core.
- Nessuna policy centralizzata OCI per allowlist/TLS/insecure.
- Query non usa lock install locale (selected_model/retriever).
- Discovery provider (`/v1/models` + probe + cache TTL) non implementata.
- Embed CLI è gestita da parser delegato (`cpm_cli/cli.py`) invece che builtin modulare registry-based.

## Interfacce Esistenti Riutilizzabili
- Registry di feature e dispatch: `cpm_core/registry/*`, `cpm_cli/main.py`.
- Manifest packet: `cpm_core/packet/models.py` (`PacketManifest`) con supporto `extras`.
- Lockfile build: `cpm_core/packet/lockfile.py` (riusabile come base concettuale).
- Workspace layout e config layering: `cpm_core/workspace.py`.
- Embeddings config + env resolution: `cpm_builtin/embeddings/config.py`.

## File Previsti da Toccare
- Core OCI:
  - `cpm_core/oci/__init__.py`
  - `cpm_core/oci/client.py`
  - `cpm_core/oci/types.py`
  - `cpm_core/oci/errors.py`
  - `cpm_core/oci/security.py`
- Config/runtime:
  - `cpm_core/workspace.py` (config defaults, eventuale wiring runtime)
  - `cpm_core/config.py` (se necessario)
- Nuovi builtin commands:
  - `cpm_core/builtins/install.py`
  - `cpm_core/builtins/publish.py`
  - `cpm_core/builtins/embed.py`
  - `cpm_core/builtins/__init__.py`
- Query updates:
  - `cpm_core/builtins/query.py`
- Packet/metadata:
  - `cpm_core/packet/models.py`
  - `cpm_core/packet/io.py` (se necessario)
- Embedding discovery:
  - `cpm_builtin/embeddings/discovery.py`
  - `cpm_builtin/embeddings/config.py`
  - `cpm_builtin/embeddings/__init__.py`
- CLI bridge cleanup:
  - `cpm_cli/main.py`
- Documentazione:
  - `README.md`
  - `cpm_builtin/embeddings/README.md`
- Test:
  - `tests/test_oci_client.py`
  - `tests/test_embed_discovery.py`
  - `tests/test_install_flow.py`
  - `tests/test_publish_flow.py`
  - `tests/test_query_install_lock.py`
  - aggiornamenti mirati a `tests/test_entrypoint.py`

## Vincoli di Progetto Confermati
- Nessun nuovo registry server CPM.
- Uso di registry OCI standard (Harbor/GHCR/GitLab/Nexus OCI compatibili).
- Compatibilità con ORAS CLI preferita per evitare dipendenze OCI complesse.

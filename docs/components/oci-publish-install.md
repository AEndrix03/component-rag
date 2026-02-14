# OCI Publish And Install

## Publish
`PublishCommand` costruisce layout OCI (`build_oci_layout`) e invia artifact con `OciClient.push`.
Supporta `--no-embed` per distribuire packet senza vettori/FAISS.

## Install
`InstallCommand`:
1. risolve ref OCI,
2. scopre referrer OCI (API referrers, fallback tag-based),
3. valuta trust report (signature/SBOM/provenance + trust score),
4. scarica artifact,
5. copia payload in `.cpm/packages/<name>/<version>`,
6. seleziona provider/modello embedding (se necessario),
7. scrive install lock.

## Verification e lock evoluto
- default strict fail-closed (`strict_verify=true`):
  - firma mancante/non valida -> errore
  - SBOM mancante -> errore
  - provenance mancante -> errore
- lock install esteso con:
  - `sources[]` (uri, digest, signature, sbom, provenance, slsa_level, trust_score)
  - `verification` completo
  - campi legacy mantenuti per compatibilita.

## Sicurezza
`cpm_core/oci/security.py` applica allowlist host, path safety e redazione token nei log.

## Operativita
Configurare `[oci]` in config (repository, retry, timeout, credenziali) prima di publish/install.

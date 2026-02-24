# Embeddings Subsystem

## Configurazione provider
`EmbeddingsConfigService` legge/scrive `.cpm/config/embeddings.yml`, gestendo provider, default e cache discovery.

## Discovery
`discovery.py` aggiorna metadati provider (modelli disponibili, dimensioni supportate) con TTL cache.

## Client runtime
`EmbeddingClient` risolve endpoint/modalita e invia richieste a backend HTTP.
`OpenAIEmbeddingsHttpClient` gestisce serializzazione payload, parse risposta, hint headers e normalizzazione embeddings.
Il controllo `EmbeddingClient.health()` considera il provider raggiungibile quando riceve qualsiasi risposta HTTP (anche `405/501` su `OPTIONS`), per evitare falsi negativi su adapter che non implementano `OPTIONS` ma servono correttamente `POST /v1/embeddings`.

## Regole pratiche
- Preferire provider default esplicito.
- Versionare cambi modello nelle note di rilascio.
- Validare health provider prima di build massivi:
```powershell
cpm embed test --name <provider>
```

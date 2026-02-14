# Query Flow

## Entry point
`QueryCommand.run()` risolve workspace, lock install, retriever richiesto/suggerito e trasporto embedding.

## Pipeline
1. risoluzione retriever (`default` o plugin),
2. fallback automatico se retriever suggerito non presente,
3. opzionale: risoluzione `--source` (`dir://`, `oci://`, `https://`) con fetch lazy in cache CAS locale (`.cpm/cache/objects/<digest>`),
4. invocazione retriever con indexer/reranker selezionati,
5. output testuale o JSON.

## Retriever nativi
- `NativeFaissRetriever`
- indexer `FaissFlatIPIndexer`
- reranker `NoopReranker` / `TokenDiversityReranker`

## Osservazioni
Il flusso e robusto a install lock incompleti e a plugin mancanti, mantenendo fallback al retriever di default.
Quando viene usato `--source`, `query` materializza prima un packet locale in cache e poi interroga il retriever nativo su quel path.

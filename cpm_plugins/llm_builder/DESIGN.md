# cpm-llm-builder Design Notes

## Current Pipeline (v2 foundation)

1. Ingest file text.
2. Classify file type/language/mime.
3. Deterministic pre-chunking (code/doc/json/text).
4. LLM enrichment via OpenAI-like envelope over HTTP.
5. Postprocess split/merge by token constraints.
6. Validate chunks and collect warnings.
7. Cache v2:
   - file-level segmentation cache
   - segment-level enrichment cache
8. Produce CPM packet artifacts with embedding incremental reuse.

## Compatibility

- Supports legacy chunk responses:
  - `["chunk1", "chunk2"]`
  - `{"chunks": [...]}`
- Supports OpenAI-like envelopes with `output_json`.

## Future

- Java AST parser integration (tree-sitter) can replace regex pre-chunker.
- Circuit breaker and advanced transport options can be layered into `llm_client.py`.

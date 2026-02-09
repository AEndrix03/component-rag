# cpm-llm-builder

`cpm-llm-builder` is a CPM plugin that builds packets with a deterministic pre-chunk pipeline and LLM enrichment over HTTP.

## Pipeline

1. Ingest files.
2. Classify file type/language/mime.
3. Deterministic pre-chunk:
   - `java`
   - `code_generic`
   - `markdown/html`
   - `json/yaml`
   - `text`
4. LLM enrichment (metadata, title, summary, tags, relations).
5. Postprocess split/merge by token constraints.
6. Quality validation.
7. Cache v2 (file + segment enrichment).

## Endpoint Contract

The plugin sends an OpenAI-like envelope:

```json
{
  "model": "chunker-xxx",
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "instructions"},
        {
          "type": "input_json",
          "json": {
            "task": "chunk.enrich",
            "source": {"path": "...", "language": "java", "mime": "text/x-java", "hash": "..."},
            "segments": [{"id": "...", "kind": "method", "text": "...", "start": 10, "end": 20}],
            "constraints": {"max_chunk_tokens": 800, "min_chunk_tokens": 120, "max_segments_per_request": 8}
          }
        }
      ]
    }
  ],
  "metadata": {"cpm_plugin": "cpm-llm-builder", "prompt_version": "chunk_enrich_v1"}
}
```

Accepted response formats:
- OpenAI-like:
```json
{"output":[{"type":"output_json","json":{"chunks":[{"id":"...","text":"..."}]}}]}
```
- Legacy:
```json
{"chunks":[{"id":"...","text":"..."}]}
```
or
```json
["chunk text 1", "chunk text 2"]
```

## Config

`config.yml`:

```yaml
llm:
  endpoint: "http://127.0.0.1:9000/chunk"
  model: "chunker-xxx"
  prompt_version: "chunk_enrich_v1"
  max_retries: 2
request_timeout: 30.0
constraints:
  max_chunk_tokens: 800
  min_chunk_tokens: 120
  max_segments_per_request: 8
```

## Run

```bash
cpm llm:cpm-llm-builder ./docs --destination ./out/packet
```

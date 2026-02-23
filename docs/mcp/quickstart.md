# MCP Quickstart

## 1. Set Environment

```powershell
$env:REGISTRY="registry.local/project"
$env:CPM_ROOT=".cpm"
$env:EMBEDDING_URL="http://127.0.0.1:8876"
$env:EMBEDDING_MODEL="mixedbread-ai/mxbai-embed-large-v1"
```

## 2. Start MCP Server

```powershell
cpm mcp:serve
```

Optional one-shot overrides:

```powershell
cpm mcp:serve --registry registry.local/project --cpm-dir .cpm --embed-url http://127.0.0.1:8876 --embed-model mixedbread-ai/mxbai-embed-large-v1
```

## 3. Recommended Tool Flow

1. `lookup` to get `pinned_uri`.
2. `query` using that `pinned_uri`.
3. Optionally use `plan_from_intent` or `evidence_digest`.

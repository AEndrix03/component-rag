# Suggested Commands (Windows / PowerShell)
# Environment setup
- `python -m venv .venv`
- `.venv\Scripts\activate`
- `pip install -e ./cpm` (or `./embedding_pool`, `./registry`)

# CPM core
- `cpm init`
- `cpm build --input-dir ./docs --packet-dir ./packets/example --model jina-en --version 1.0.0`
- `cpm query --packet example --query "..." -k 5`
- `cpm publish --from ./packets/my-knowledge-base --registry http://localhost:8786`
- `cpm install my-knowledge-base@1.0.0 --registry http://localhost:8786`

# Embedding providers
- `cpm embed add --name local --url http://127.0.0.1:8876 --set-default`
- `cpm embed list`
- `cpm embed test --text "hello"`

# Registry server
- `cpm-registry start --detach`
- `cpm-registry status`

# MCP server
- `cpm mcp serve`

# Tests
- `pytest`

# Useful PowerShell utilities
- `Get-ChildItem` (list files)
- `Get-ChildItem -Recurse` (recursive list)
- `Select-String -Pattern "..." -Path **\*.py` (search)
- `Set-Location` / `cd` (change directory)
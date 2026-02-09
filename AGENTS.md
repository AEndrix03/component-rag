# Repository Guidelines

## Project Structure and Module Organization
- `cpm_core/`: Core app lifecycle, workspace, registry, plugin runtime, built-in command registration.
- `cpm_cli/`: CLI routing/dispatch layer.
- `cpm_builtin/`: Built-in features (chunking, embeddings config, package manager helpers).
- `cpm_plugins/`: Official plugins, including MCP integration.
- `registry/`: Externalized registry package (maintained separately from core runtime evolution).
- `.cpm/`: Local runtime configuration/state created by `cpm init`.
- `.venv/`: Local virtual environment (not tracked).

## Build, Test, and Development Commands
- `python -m venv .venv` and `pip install -e .` (or `pip install -e ".[dev]"`): set up editable install.
- `cpm init`: create workspace config under `.cpm/config/`.
- `cpm embed add --name local --url http://127.0.0.1:8876 --set-default`: register the local embedding endpoint.
- `cpm build --source ./docs --name example --packet-version 1.0.0`: build a packet with the modular build command.
- `cpm query --packet example --query "..." -k 5`: query a packet.
- `pytest`: run tests.

## Coding Style and Naming Conventions
- Python 3.11+, type hints encouraged.
- Ruff/Black are configured in root `pyproject.toml` (line length 120).
- Module and function names use `snake_case`; classes use `PascalCase`.

## Testing Guidelines
- Pytest configuration lives in root `pyproject.toml`.
- Test file patterns: `test_*.py` or `*_test.py`.
- Add tests under `tests/` (or component-local suites when introduced).

## Commit and Pull Request Guidelines
- Commit history mixes conventional prefixes (`feat:`) and short informal messages (`wip`, `amend`). Use concise, present-tense summaries; prefer `type: summary` for new work.
- PRs should include: a clear description, linked issues (if any), and steps to run or verify locally.
- If you touch config or storage, call it out explicitly (for example, `.cpm/*`, `registry/.env`, or `registry/registry.db*`).

## Configuration and Data Notes
- Local config is under `.cpm/config/` (`config.yml`, `embeddings.yml`).
- Registry runtime may use SQLite files in `registry/`; avoid committing DB artifacts unless explicitly required.

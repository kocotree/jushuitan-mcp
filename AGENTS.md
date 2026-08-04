# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `src/jst_connector/`. `client.py` owns the read-only Jushuitan API methods and endpoint whitelist; `config.py`, `signing.py`, and `token_cache.py` handle configuration, request signing, and token persistence. User-facing entry points are `cli.py` (`jst`) and `mcp_server.py` (`jst-mcp`). The public surface covers inventory, orders, purchases, purchase inbound, SKU products, and style products; shop queries are intentionally excluded. Tests live in `tests/` and mirror these modules.

## Build, Test, and Development Commands

Use PowerShell from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m jst_connector.cli --help
.\.venv\Scripts\python.exe -m jst_connector.mcp_server
```

The editable install exposes `jst` and `jst-mcp`. Run a focused test with `python -m pytest tests/test_client.py -q`.

## Coding Style & Naming Conventions

Target Python 3.10 or newer. Use four-space indentation, type hints for public interfaces, and concise docstrings for MCP tools. Follow standard Python naming: `snake_case` for functions and modules, `PascalCase` for classes, and uppercase names for constants. Keep API parameters aligned with official Jushuitan names; translate to Python style only at the public boundary (for example, `load_sku_bin` becomes `loadSkuBin` in the request). No formatter or linter is currently enforced, so keep diffs consistent with surrounding code and run `git diff --check`.

## Testing Guidelines

Tests use `pytest` and should be named `test_<behavior>`. Cover public client behavior, CLI parsing/execution, and MCP tool exposure. Use `httpx.MockTransport`; automated tests must not require live credentials or network access. For fixes and new endpoints, add a failing regression test before implementation. Run the full suite before submitting changes.

## Commit & Pull Request Guidelines

History uses Conventional Commit-style subjects, such as `feat: add purchase inbound and product queries`. Keep each commit scoped and imperative; use prefixes such as `feat:`, `fix:`, `test:`, or `docs:`. Pull requests should explain the behavior change, list verification commands, link the relevant official API documentation, and note any configuration impact. Include screenshots only for user-visible documentation changes where they add value.

## Security & Configuration

Copy `.env.example` to `.env`; never commit keys, secrets, tokens, or real API payloads. Preserve `READ_ONLY_PATHS` as an explicit whitelist. Adding any write endpoint requires separate approval and must not be bundled with a read-only feature.

# T06-crawl-cli-and-docs

## Context

Wire the crawler into the CLI so users can run `folio crawl <url>` with sensible defaults and documented flags.

## Scope

- `folio crawl <url>` subcommand with `--output`, `--delay`, `--max-pages`, `--skip-login-wait`
- README usage section for crawl workflow
- Root `.gitignore` for `output/`

## Implementation plan (required before coding)

### Planned approach

1. Extend `folio/cli.py` with `crawl` subparser and dispatch to `run_crawl`
2. Update README with crawl example (example.com)
3. Add `.gitignore`
4. CLI tests with mocked `run_crawl`

### Files to touch

- `src/folio/cli.py`: crawl subcommand
- `README.md`: crawl documentation
- `.gitignore`: ignore output and caches
- `tests/test_cli.py`: crawl command tests

### Data and API impact

- New CLI command `folio crawl`

### Risks and mitigations

- Risk: User crawls without permission
  Mitigation: document responsible use in README

### Verification plan (ticket-specific)

- Automated: `uv run pytest`, `uv run ruff check .`, `uv run mypy`
- Manual: `folio crawl https://www.example.com/`

## Acceptance criteria

- [x] `folio crawl --help` documents all flags
- [x] CLI dispatches to crawler with parsed options
- [x] README documents login-then-Enter workflow
- [x] Sprint 2 artifacts closed

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run mypy`
- [ ] Manual example.com crawl

## Status

- Owner: agent
- State: Done

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T06-crawl-cli-and-docs.md`.

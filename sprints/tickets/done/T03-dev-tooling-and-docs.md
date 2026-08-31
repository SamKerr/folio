# T03-dev-tooling-and-docs

## Context

The project needs repeatable quality checks and documentation so new contributors can set up and verify the scaffold quickly.

## Scope

- pytest tests for CLI (version, help, doctor with mock)
- ruff configuration in pyproject.toml
- Update README and AGENTS.md with concrete commands
- Close sprint artifacts

## Implementation plan (required before coding)

### Planned approach

1. Add `tests/test_cli.py` covering version, help, and doctor error path
2. Configure ruff in `[tool.ruff]` section of pyproject.toml
3. Update README with setup, doctor, test, and lint commands
4. Run full verification suite and close sprint

### Files to touch

- `tests/test_cli.py`: CLI tests
- `tests/conftest.py`: shared fixtures if needed
- `pyproject.toml`: ruff config
- `README.md`, `AGENTS.md`: verification commands

### Data and API impact

- None

### Risks and mitigations

- Risk: Doctor integration test requires browsers in CI
  Mitigation: mock Playwright in unit tests; manual doctor for full check

### Verification plan (ticket-specific)

- Automated: `pytest`, `ruff check .`
- Manual: follow README setup steps from scratch

## Acceptance criteria

- [x] `pytest` passes
- [x] `ruff check .` passes
- [x] README documents full setup and verification workflow
- [x] Sprint 1 plan and tickets closed and moved to `done/`

## Implementation notes (during/after execution)

- Five CLI tests; version/help use `pytest.raises(SystemExit)` because argparse exits
- ruff configured for py311 with E, F, I, UP rules

## Verification

- [x] `pytest`
- [x] `ruff check .`
- [x] README setup steps verified

## Status

- Owner: agent
- State: Done

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T03-dev-tooling-and-docs.md`.

# T01-project-packaging

## Context

The repo has docs and sprint workflow but no Python code. We need a standard installable package before adding CLI or crawler logic.

## Scope

- Add `pyproject.toml` with runtime deps (playwright) and dev extras (pytest, ruff)
- Create `src/folio/` package with `__init__.py` exposing version
- Configure `[project.scripts]` entry point for `folio` CLI (stub until T02)

## Implementation plan (required before coding)

### Planned approach

1. Add `pyproject.toml` using setuptools with `src` layout
2. Create `src/folio/__init__.py` with `__version__`
3. Add minimal `cli.py` stub so entry point resolves

### Files to touch

- `pyproject.toml`: project metadata, dependencies, scripts, tool config
- `src/folio/__init__.py`: version constant
- `src/folio/cli.py`: minimal argparse stub

### Data and API impact

- None

### Risks and mitigations

- Risk: Python version mismatch on developer machines
  Mitigation: require `>=3.11` in pyproject.toml

### Verification plan (ticket-specific)

- Automated: `pip install -e ".[dev]"` succeeds
- Manual: `python -c "import folio; print(folio.__version__)"`

## Acceptance criteria

- [x] `pyproject.toml` exists with playwright dependency and dev extras
- [x] `src/folio/` package is importable after editable install
- [x] Version is exposed as `folio.__version__`

## Implementation notes (during/after execution)

- Used setuptools src layout with `folio` package at `src/folio/`
- Version `0.1.0` in both `pyproject.toml` and `__init__.py`

## Verification

- [x] `pip install -e ".[dev]"` succeeds
- [x] Import and version check pass

## Status

- Owner: agent
- State: Done

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T01-project-packaging.md`.

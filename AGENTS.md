# AGENTS.md

## Project

- **Project name:** Folio
- **Primary codebase:** `src/` (planned) — Python, Playwright for headless browsing
- **Backend/services:** None (CLI tool; optional local static server for preview only)
- **Main docs:** `README.md`, `.cursor/rules/project-conventions.md`

## High-level structure

- `src/folio/` — crawler, link discovery, HTML persistence, CLI entrypoint
- `output/` — default extraction target directory (gitignored)
- `sprints/plans/` — active sprint plans (move completed plans to `sprints/plans/done/`)
- `sprints/tickets/` — active sprint tickets (move completed tickets to `sprints/tickets/done/`)
- `.cursor/agents/` — optional subagent persona definitions
- `.cursor/rules/` — Cursor rules (sprint workflow, project conventions)
- `examples/lockedin/` — reference for filling in agent/docs sections from the Cursor template

See `examples/lockedin/AGENTS.project-section.md` for a filled-in example from another project.

## How to work

- Confirm scope and constraints with the user before large, medium, or multi-step changes
- Confirm the requirements and the goals of the sprint if it is not clear
- If part way through execution of a task you come across ambiguity, reach out to the user to clarify
- Keep changes focused, incremental, and easy to verify
- Prefer the simplest solution that fits existing app patterns
- Do not change unrelated behavior
- Do not revert user work; integrate with existing in-progress changes carefully
- Update docs when developer commands, setup, or behavior change

## Sprint workflow

Use this process for multi-step feature work so planning and delivery stay consistent.

**Sprint artifact closure is part of the deliverable.** Do not consider a ticket or sprint finished until its markdown files are updated and moved to the correct `done/` folder.

Active artifacts live in `sprints/plans/` and `sprints/tickets/`. Completed artifacts live in `sprints/plans/done/` and `sprints/tickets/done/`. Create those `done/` directories if they do not exist.

### Required lifecycle

1. Clarify scope and lock product constraints with the user. Clarify anything that is ambiguous.
2. Create/update the active sprint plan in `sprints/plans/`:
   - file name format: `sprint-<n>.md` (example: `sprint-3.md`)
   - include scope, ticket list, sequencing, and done criteria
   - use `sprints/plans/sprint-template.md` as baseline when available
3. Create or update sprint ticket files in `sprints/tickets/`:
   - one file per active ticket (`Txx-<short-title>.md`)
   - include acceptance criteria, verification notes, and a ticket-level implementation plan
   - implementation plan must include: planned steps, files to touch, data/API impact, risks/mitigations, and ticket-specific verification
4. Implement in sensible commit-sized chunks (small, coherent changes).
5. Verify each chunk before moving to the next one:
   - run relevant tests/checks
   - confirm expected behavior for changed screens/flows
   - fix regressions immediately before continuing
6. **Close each ticket immediately after its acceptance criteria pass** (do not wait for the whole sprint):
   - check off acceptance criteria and verification items in the ticket file
   - set `State: Done` in the ticket `Status` section
   - check off the ticket in the sprint plan (`- [x]`)
   - move the ticket file: `sprints/tickets/Txx-<title>.md` -> `sprints/tickets/done/Txx-<title>.md`
7. **Close the sprint when all in-scope tickets are in `sprints/tickets/done/`**:
   - summarize outcomes in the sprint plan (brief notes under `## Notes` if helpful)
   - move the sprint plan: `sprints/plans/sprint-<n>.md` -> `sprints/plans/done/sprint-<n>.md`
8. Update docs whenever commands, behavior, or process changes.

### Multi-sprint request rule (mandatory)

- If a user request explicitly references multiple sprint numbers (for example "Sprint 10", "Sprint 11", "Sprint 12"), create separate sprint plan files for each sprint number.
- Use one plan file per sprint number (`sprint-10.md`, `sprint-11.md`, `sprint-12.md`, etc.) in `sprints/plans/`.
- Do not merge multiple sprint numbers into a single sprint plan file.
- Keep ticket artifacts split by sprint scope and close/move them independently.
- If dependencies exist across sprints, document cross-sprint ordering in each sprint plan's sequencing/notes while still preserving one-file-per-sprint.

### Pre-implementation gate (mandatory)

- Before writing implementation code, complete this checklist:
  - [ ] Sprint plan and ticket file exist for the work item
  - [ ] Ticket implementation plan section is filled in with concrete steps/files/verification
- If any item is unchecked, do not start coding until the gap is fixed.

### Sprint closure checklist

Run this before ending a sprint session or marking work complete:

- [ ] Every finished ticket has acceptance criteria checked and `State: Done`
- [ ] Every finished ticket file is in `sprints/tickets/done/`
- [ ] Sprint plan ticket list uses `- [x]` for completed tickets
- [ ] Sprint plan file is in `sprints/plans/done/` when the sprint is finished
- [ ] Only the active sprint plan and its open tickets remain in `sprints/plans/` and `sprints/tickets/`

## How to verify changes

- Install deps: `uv sync --group dev`
- Install Playwright browsers: `uv run playwright install chromium`
- Run quality checks for affected code:
  - `uv run pytest`
  - `uv run ruff check .`
  - `uv run mypy`
- Manual verification: `uv run folio doctor` (confirms Playwright/Chromium work)

## Safety

- Keep docs/scripts updated when commands or behavior change
- Never commit secrets or `.env` values
- Never edit user-owned draft docs (e.g. personal roadmaps) unless explicitly asked
- Crawl only sites you are allowed to access; rate-limit requests when implementing the crawler

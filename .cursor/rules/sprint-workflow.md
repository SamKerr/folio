# Sprint workflow (required)

When working on sprint tickets, artifact closure is part of the deliverable — not optional housekeeping.

## Active vs done

- Active: `sprints/plans/`, `sprints/tickets/`
- Done: `sprints/plans/done/`, `sprints/tickets/done/`
- Create `done/` directories if missing.

## When a ticket is finished

1. Check off acceptance criteria and verification items in the ticket file.
2. Set `State: Done` in the ticket `Status` section.
3. Check off the ticket in the sprint plan (`- [x]`).
4. Move the file: `git mv sprints/tickets/Txx-*.md sprints/tickets/done/`

Do this immediately after verification passes — do not wait until the whole sprint is done.

## When a sprint is finished

1. Confirm all in-scope tickets are in `sprints/tickets/done/`.
2. Move the plan: `git mv sprints/plans/sprint-<n>.md sprints/plans/done/`
3. Only the current active sprint plan and its open tickets should remain outside `done/`.

## Full lifecycle

See `AGENTS.md` for the complete sprint workflow and sequencing rules.

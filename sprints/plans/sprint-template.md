# Sprint <n> - <name>

## Scope

- <what is in scope>
- <what is explicitly out of scope>

## Tickets

- [ ] `T01-<title>`
- [ ] `T02-<title>`

## Sequencing

1. <first dependency / first ticket>
2. <next ticket>
3. <final ticket>

## Done criteria

- All in-scope tickets marked complete
- Relevant tests/lint/typecheck pass
- User-facing behavior verified on impacted screens
- Docs updated if commands/setup/behavior changed

## Verification plan

- `npm test` (or targeted `npx jest <path>`)
- `npm run lint`
- `npm run typecheck`
- Manual app flow checks for impacted screens

## Notes

- <risks, assumptions, follow-ups>

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-<n>.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.

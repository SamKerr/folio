# Project conventions

Copy this file to `project-conventions.md` and customize for your repository.

## Overview

- **Project:** `<project name and one-line description>`
- **Primary platform:** `<e.g. web, mobile, CLI, API>`

## Tech stack

- **Language:** `<e.g. TypeScript, Python, Go>`
- **Framework:** `<e.g. React Native, Next.js, FastAPI>`
- **State management:** `<e.g. Redux Toolkit, Zustand, none>`
- **Backend:** `<e.g. Supabase, Postgres, REST>`
- **Styling:** `<e.g. theme tokens, Tailwind, CSS modules>`

## Project structure

```
<root>/
├── <src-or-app>/     # Main application code
├── <tests>/          # Test layout (if separate)
├── docs/             # Developer docs
└── sprints/          # Sprint plans and tickets
```

Document your folder conventions here. Include import path aliases if used.

## Code patterns

### Components / modules

- Prefer `<functional components | classes | modules>` consistent with the codebase
- Keep modules focused with explicit interfaces
- Use `<testID | data-testid | aria-*>` for testable UI elements

### State and data

- Where API calls live: `<e.g. Redux thunks, service layer, hooks>`
- Error handling conventions
- Naming conventions for slices/stores/services

### Imports

- Path alias: `<e.g. @/ for src/>`
- Import order: React/runtime, external libs, internal modules

### Styling

- Reference design tokens; avoid hardcoded colors/spacing where a theme exists
- Naming conventions for styles

### Naming conventions

- Components: `<PascalCase>`
- Utilities: `<camelCase>`
- Tests: `<*.test.ts, __tests__/, etc.>`

## External services

- How clients are initialized
- Environment variable naming
- Where secrets must never appear

## Testing

- Test file location convention
- Mocking strategy for external services
- Minimum verification before merge

## Environment

- Env file naming (`.env.development`, etc.)
- How config is loaded in dev vs prod

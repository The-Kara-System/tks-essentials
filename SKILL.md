# Repository Intelligence for Codex

Use this file as the default operating contract for engineering work in this repository.

## Primary Goal
Deliver production-safe, minimal-surface improvements to shared TKS primitives while
preserving contracts consumed by peer repositories.

## Core Engineering Discipline
- Prefer correctness first, then simplicity.
- Keep logic explicit and easy to trace.
- Keep code small enough to reason about directly.
- Keep code as small as possible to get the job done, but not smaller.
- Preserve API behavior unless a scoped request says otherwise.

## Context Priorities
1. `README.md`
2. `TESTING.md`
3. `tksessentials/data_models/README.md`
4. `AGENTS.md`
5. Relevant files in `agents/*.md`

## Scope Boundaries
- Allowed default edits: `tksessentials/**`, `tests/**` directly tied to requested changes.
- Avoid editing peer repositories by default (`tks-strategy-framework`,
  `tks-strategy-fractals`, `tks-bridge-binance-spot-public`).
- Avoid broad refactors unless explicitly requested.

## Task Routing (Codex Execution)
- Data model or lifecycle behavior:
  - `agents/data-models.md`
- Kafka/DB/helpers and external integration:
  - `agents/integration-io.md`
- Testing and release-tooling workflow:
  - `agents/quality.md`
- Any doc/README-only onboarding change:
  - `agents/codex-onboarding.md` (or closest matching doc note)

## Completion Standard
- Behavior changes are covered by targeted tests.
- Cross-repo contract implications are documented in the same change set.
- No assumption is left unbounded in the changed runtime path.
- Final notes identify what was changed and why.

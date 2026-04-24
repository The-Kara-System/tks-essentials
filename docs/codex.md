# Codex Onboarding for tks-essentials

Start here before any scoped edit.

## Read Order
1. `README.md`
2. `TESTING.md`
3. `tksessentials/data_models/README.md` (for model changes)
4. `AGENTS.md`
5. `SKILL.md`
6. Relevant file in `agents/`

## Agent Routing
- Data model contract changes:
  - `agents/data-models.md`
- Integration/database/config I/O changes:
  - `agents/integration-io.md`
- Testing, CI, and verification updates:
  - `agents/quality.md`

## Guardrails to Enforce
- Keep code simple.
- Keep code maintainable.
- Keep it as small as possible to get the job done, but not smaller.
- Preserve cross-repo contracts by default.

## Escalation Triggers
- New event/payload field addition that changes producer/consumer behavior.
- Topic-related or broker bootstrap behavior changes.
- Any behavior change with compatibility impact on:
  - `tks-strategy-framework`
  - `tks-strategy-fractals`
  - `tks-bridge-binance-spot-public`

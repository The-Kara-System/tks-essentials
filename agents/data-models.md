# data-models

## Ownership
- `tksessentials/data_models/payloads.py`
- `tksessentials/data_models/events.py`
- `tksessentials/data_models/snapshots.py`
- `tksessentials/data_models/value_objects.py`
- `tksessentials/data_models/__init__.py`

## Goal
- Keep business meaning explicit between payloads, events, and snapshots.
- Preserve the lifecycle contract used by frameworks and bridges.

## Entry Checklist
- Confirm noun-vs-fact modeling has not been blurred:
  - payloads = business nouns
  - events = immutable facts
  - snapshots = read-model summaries
- Keep `Signal` and `Order`/`Trade` transitions aligned with peer repos.
- Keep `extra="forbid"` and validation strictness unless explicitly asked to relax it.
- Preserve field naming and IDs needed for traceability (`signal_id`, `intent_id`,
  `signal_provider_*`, correlation fields).
- Verify helper methods remain semantically stable (e.g., terminal checks, sizing semantics).

## Boundaries
- Do not rename contract-level enums/fields without explicit user approval.
- Do not change serialization-sensitive defaults unless needed and documented.
- If adding new contract models, add explicit event-scenario tests and docs updates.

## Change Acceptance
- If adding/changing models, update tests in `tests/test_data_models.py`.
- If changing rejection/cold/hot signal behavior, validate compatibility with
  `tks-strategy-framework` and `tks-bridge-binance-spot-public`.

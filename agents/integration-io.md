# integration-io

## Ownership
- `tksessentials/database.py`
- `tksessentials/utils.py` (runtime config and service env paths)
- Integration helpers and I/O-facing utilities.

## Goal
- Keep integration behavior deterministic across local, CI, and deployment contexts.
- Preserve compatibility for services that import these utilities from peer repos.

## Entry Checklist
- Check env var and root-path behavior before changing defaults.
- Keep topic/bootstrap behavior deterministic.
- Preserve external client behavior (`aiokafka` path, connection retries, serialization expectations).
- Keep failures explicit: errors should be actionable for deployers.
- If touching integration behavior, add explicit tests in:
  - `tests/test_database*.py`
  - `tests/test_utils.py`
  - `tests/test_database_integration.py` where relevant.

## Boundaries
- No topic-name or payload contract changes without explicit approval.
- Keep integration code as simple as possible; avoid broad abstraction layers.
- Ensure configuration changes remain backward compatible.

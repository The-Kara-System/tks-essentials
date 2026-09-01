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

## Shared Kafka and ksqlDB Contract
- Use `database.get_kafka_client_kwargs()` for every `aiokafka` producer,
  consumer, admin, availability, and snapshot path.
- Use `database.get_ksqldb_httpx_kwargs()` for every ksqlDB HTTP client or
  request. Continue to use `database.get_ksqldb_url()` for endpoint paths.
- DEV defaults remain `localhost:9092`/PLAINTEXT and
  `http://localhost:8088`/unauthenticated.
- UAT/PROD require `SASL_SSL` plus `SCRAM-SHA-512` for Kafka, HTTPS plus Basic
  Auth for ksqlDB, mounted password files, and mounted CA files. Missing or
  partial configuration must not fall back to localhost or plaintext.
- Contract variables are documented in `README.md`. Do not add plaintext
  password environment-variable fallbacks.
- This is a cross-repo runtime contract addition. Consumers must upgrade to the
  next published `tks-essentials` patch release before their SAHRI Kafka cutover.

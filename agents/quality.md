# quality

## Ownership
- `tests/*`
- `TESTING.md`
- CI workflow behavior in `.github/workflows/testing_and_deployment.yml`

## Goal
- Keep confidence high while keeping feedback tight.
- Ensure model-level behavior changes have targeted tests first.

## Default Verification Focus
- Add/adjust tests in the smallest relevant module test file before behavior changes.
- For critical paths, run:
  - module-level tests first
  - then suite-level tests
  - then integration tests only if required by scope.

## Entry Checklist
- Validate changes to:
  - test count and coverage expectations
  - integration markers
  - external service assumptions (Kafka/ksqlDB)
- Keep tests readable and deterministic.
- Update coverage-relevant test names to preserve maintainability.

## Boundaries
- Do not add new testing frameworks unless a gap cannot be addressed by existing stack.
- Do not edit CI infra without linking scope to reliability or risk reduction.

# AGENTS

## Purpose
- This repository provides shared production primitives for TKS services:
  `tksessentials` utilities and `tksessentials.data_models`.
- Core consumers are `tks-strategy-framework`, `tks-strategy-fractals`, and
  `tks-bridge-binance-spot-public`.
- The primary objective is small, correct, and maintainable changes that preserve
  cross-repo contracts.

## Repo Map
- `tksessentials/data_models/*`: productive domain models (`payload`, `event`,
  `snapshot`) and value objects.
- `tksessentials/utils.py`: path/env/config helpers and metadata utilities.
- `tksessentials/validators.py`: strict input and format validators.
- `tksessentials/database.py`: Kafka/topic bootstrap and database helpers.
- `tksessentials/security.py`: crypto/config security helpers.
- `tksessentials/global_logger.py`: logging setup and naming conventions.
- `tksessentials/asset_formatter.py`: market symbol normalization helpers.
- `tksessentials/constants.py`: shared runtime constants.
- `tests/*`: unit and integration coverage, including Docker-backed Kafka scenarios.

## Top Guardrails (Non-negotiable)
- Keep the code simple.
- Keep the code maintainable.
- Keep it as small as possible to get the job done, but not smaller.
- Prefer explicit, readable logic over clever abstractions.
- Preserve behavior unless explicitly requested to change it.
- Do not change external contract names or topic names unless explicitly requested.
- Never modify peer repos by default (`tks-strategy-framework`,
  `tks-strategy-fractals`, `tks-bridge-binance-spot-public`) from this repo.

## Working Rules
- Read in this order before changing behavior:
  1. `README.md`
  2. `TESTING.md`
  3. `tksessentials/data_models/README.md`
  4. this file
  5. the relevant file under `agents/`.
- Do not edit `.venv`, `.pytest_cache`, `build`, `dist`, `htmlcov`, or generated
  artifacts unless required for an explicit task.
- Keep exception/error messages explicit and actionable.
- Do not introduce new dependencies unless removing duplication or removing risk.

## Commands
- Setup:
  - `py -m pip install -r requirements-dev.txt`
  - `py -m pytest`
- Focused verification:
  - Unit: `py -m pytest tests/test_utils.py tests/test_validators.py`
  - Full: `py -m pytest`
  - Integration: `py -m pytest tests/int`
- Build:
  - `python -m build`

## Review Checklist
- Did the change preserve the current `data_models` contract semantics?
- Did we keep event vs payload semantics clear and explicit?
- Are topic/env/broker behaviors unchanged unless in-scope?
- Are targeted tests updated or added for any behavior path changed?
- Are edits limited to the smallest scope required?

## Done Means
- Required `agents/*` file for the touched area exists in scope.
- Targeted tests are updated and pass logically with the behavior change.
- No unrelated files are modified.
- Any cross-repo contract impact is documented in the related agent note and PR
  summary.

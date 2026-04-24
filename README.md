# tks-essentials

A library with essentials needed in every backend Python app, including logging, local database connection helpers, filtering, and formatting utilities.

## Sponsors

Freya Alpha,
The Kára System,
Spark & Hale Robotic Industries

## Requirements

This package currently requires `Python 3.12.9` or newer.

## Installation

Install from PyPI:

```powershell
python -m pip install tks-essentials
```

Import the package without the dash:

```python
from tksessentials import global_logger
```

## Trading Models

`tksessentials.data_models` is the productive model package for event-driven trading flows. It separates payload nouns from event facts and snapshots, and it models the full path from a local strategy intent to a closed trade.

The package is grouped like this:

```text
tksessentials/
  data_models/
    value_objects.py   # enums and tiny reusable structs
    payloads.py        # durable business nouns
    events.py          # immutable past-tense facts
    snapshots.py       # read-side projections
```

The detailed package reference now lives in `tksessentials/data_models/README.md`.

### Core Design Rules

1. Payloads are nouns.
   Examples: `TradingSignalIntent`, `TradingSignal`, `OrderRequest`, `OrderFill`, `Trade`.
2. Events are past-tense facts.
   Examples: `TradingSignalIntentGranted`, `TradingSignalCreated`, `OrderPlaced`, `TradeClosed`.
3. A `TradingSignalIntent` is local and pre-PRM.
   It exists inside the strategy pod and may never leave it.
4. A `TradingSignal` is PRM-granted and transport-ready.
   It is the Kafka contract consumed by bridge services.
5. Orders are execution instructions, not trades.
6. Trades are built from execution reality, not from signal wishfulness alone.

### Architecture Map

```text
MODEL LAYERS
============

STRATEGY POD / LOCAL WRITE SIDE               PRM GATE + CROSS-SERVICE SIGNAL            EXECUTION LAYER                          TRADE AGGREGATE / READ SIDE
----------------------------------+           +----------------------------------+       +----------------------------------+     +----------------------------------+
| Payload: TradingSignalIntent     |           | Payload: TradingSignal           |       | Payload: OrderRequest            |     | Payload: Trade                   |
| local pre-PRM signal draft       |           | PRM-granted Kafka contract       |       | one concrete venue instruction   |     | position/trade business object   |
+----------------+-----------------+           +----------------+-----------------+       +----------------+-----------------+     +----------------+-----------------+
                 |                                                  |                                      |                                        ^
                 | wrapped by events                                | wrapped by events                    | produces fills                           |
                 v                                                  v                                      v                                        |
+----------------------------------+           +----------------------------------+       +----------------------------------+     +----------------------------------+
| TradingSignalIntent events       |           | TradingSignal events             |       | Order events                     |     | Trade events                     |
| - TradingSignalIntentCreated     |           | - TradingSignalCreated           |       | - OrderRequested                 |     | - TradeOpened                    |
| - TradingSignalIntentGranted     |           | - TradingSignalRejected          |       | - OrderPlaced                    |     | - TradeIncreased                 |
| - TradingSignalIntentRejected    |           | - TradingSignalQualifiedCold     |       | - OrderPartiallyFilled           |     | - TradeReduced                   |
| - TradingSignalIntentCanceled    |           | - TradingSignalQualifiedHot      |       | - OrderFilled                    |     | - TradeClosed                    |
| - TradingSignalIntentExpired     |           | - TradingSignalInvalidated       |       | - OrderCanceled                  |     | - TradeCanceled                  |
+----------------+-----------------+                                                    | - OrderRejected                  |     | - ProfitRealized                 |
                 |                                                                      +----------------+-----------------+     +----------------+-----------------+
                 |                                                                                       |                                        ^
                 |                                                                                       v                                        |
                 +--------------------------------------------------------------------> +----------------------------------+       |
                                                                                        | Payload: OrderFill               | ------+
                                                                                        | one execution fact               |   used to open/update/close trade
                                                                                        +----------------------------------+


LIFECYCLE PATH
==============

  Strategy Pod
     |
     v
  TradingSignalIntent
     |
     +--> TradingSignalIntentRejected ---------------------> stop inside pod
     |
     +--> TradingSignalIntentCanceled / TradingSignalIntentExpired --> stop inside pod
     |
     +--> TradingSignalIntentGranted
             |
             v
         TradingSignal
             |
             +--> carries `created_at` and `prm_granted_at`
             |
             +--> published to Kafka
                     |
                     +--> TradingSignalCreated
                             |
                             +--> bridge consumes signal
                                     |
                                     +--> OrderRequested
                                             |
                                             +--> OrderRejected -----> stop or re-plan
                                             |
                                             +--> OrderPlaced
                                                     |
                                                     +--> OrderCanceled -> stop or retry
                                                     |
                                                     +--> OrderPartiallyFilled
                                                     |       |
                                                     |       +------------> TradeOpened / TradeIncreased / TradeReduced
                                                     |
                                                     +--> OrderFilled
                                                             |
                                                             +------------> TradeOpened
                                                             |
                                                             +------------> TradeIncreased
                                                             |
                                                             +------------> TradeReduced
                                                             |
                                                             +------------> TradeClosed
                                                                                  |
                                                                                  +--> ProfitRealized
```

### Lifecycle Vocabulary

| Term | Proposed model | Meaning | Not the same as | Typical producer | Typical next step |
| --- | --- | --- | --- | --- | --- |
| Trading signal intent | `TradingSignalIntent` | A local strategy-side draft that says "I want to emit this trading signal if PRM allows it." | Not yet a Kafka-published trading signal, not an order, and not a trade. | Strategy pod. | PRM grant, rejection, cancellation, or expiration. |
| Trading signal intent event | `TradingSignalIntentCreated`, `TradingSignalIntentGranted`, `TradingSignalIntentRejected`, `TradingSignalIntentCanceled`, `TradingSignalIntentExpired` | Facts about what happened to the local trading-signal intent before or during PRM evaluation. | Not the intent payload itself and not the eventual transport signal. | Strategy pod or local PRM service. | Materialize `TradingSignal` or stop. |
| Trading signal | `TradingSignal` | A PRM-granted, cross-service signal contract that is allowed to leave the strategy pod and be published to Kafka. | Not just an internal wish anymore, not a venue order, and not a trade. | Strategy pod after PRM approval. | Kafka publication and downstream bridge consumption. |
| Trading signal event | `TradingSignalCreated`, `TradingSignalRejected`, `TradingSignalQualifiedHot`, `TradingSignalQualifiedCold`, `TradingSignalInvalidated` | Immutable facts about what happened to a published or consumed trading signal in the platform. | Not the trading-signal payload itself and not current state. | Kafka producer, bridge, or downstream routing services. | Downstream qualification, execution, or stop. |
| Order request | `OrderRequest` | One concrete instruction to place, modify, or cancel an order on a venue. | Not a trade and not proof of execution. | Execution adapter or router. | Venue submission. |
| Order event | `OrderRequested`, `OrderPlaced`, `OrderPartiallyFilled`, `OrderFilled`, `OrderCanceled`, `OrderRejected` | Facts about what happened to one concrete venue order. | Not the overall trade lifecycle. Multiple order events may belong to one trade. | Execution adapter. | Fill handling and trade updates. |
| Fill | `OrderFill` | The actual execution fact: quantity, price, fee, side, and time for matched liquidity. | Not the order request and not the trade aggregate. One order may have many fills. | Venue adapter or broker integration. | Trade open/update/close. |
| Trade | `Trade` | The domain aggregate representing actual exposure, realized PnL, and lifecycle state over time. | Not the original signal and not one order. A trade is built from execution outcomes. | Trade aggregate or portfolio engine. | Open, scale, reduce, close, settle. |
| Snapshot | `TradingSignalSnapshot`, `TradingSignalIntentSnapshot`, `OrderSnapshot`, `TradeSnapshot` | Query-friendly materialized state built from events. | Not the source of truth and not something that should normally be published as the core business event. | Projection or read-model service. | APIs, UI, reporting, recovery. |

`signal_provider` is explicit domain identity for the signal owner or originator. It is not the same as event `source`, which should continue to mean the service that emitted the event.

`created_at` on `TradingSignalIntent` captures when the strategy formed the trading idea. `prm_granted_at` on `TradingSignal` captures when PRM allowed that idea to become a publishable signal. Both timestamps matter and answer different business questions.

### Trade Monitoring Extension

Trade monitoring is not modeled yet in the productive package, but the recommended future extension is:

- `TradeMonitoringTick`
  Purpose: realtime mark-price and PnL updates for a monitored position or signal.
- `TradeMonitoringClosed`
  Purpose: terminal monitoring event with `closed_at` and a `close_reason` such as TP or SL.

These should be added as dedicated event-facing models in `tksessentials.data_models` when the monitoring contract becomes stable, rather than as ad-hoc dict payloads in downstream projects.

## Development

For Codex and contributor workflow instructions, read `SKILL.md`, `AGENTS.md`, and `docs/codex.md` before making behavior changes (especially in `tksessentials/data_models`).

### Quick start for new developers

Use this checklist the first time you work on this repo:

1. Create and enter a virtual environment.
2. Install dependencies.
3. Run unit tests.
4. Run build checks before creating a release.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements-dev.txt
```

`requirements-dev.txt` already includes runtime requirements, so this is enough for normal dev work.

### Compile, test, and release (for junior contributors)

Use this flow for day-to-day development:

## 1) Development setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements-dev.txt
```

## 2) Make and run local checks

```powershell
python -m pytest                 # default run (unit tests + coverage)
python -m pytest --no-cov        # faster local pass without coverage
python -m pytest tests/int        # Kafka integration tests (Docker required)
python -m pip_audit -r requirements.txt -r requirements-dev.txt
```

If integration tests fail, make sure Docker is running and the local project root is resolvable:

```powershell
$env:PROJECT_ROOT = (Resolve-Path .).Path
New-Item -ItemType Directory -Force -Path .\config, .\logs | Out-Null
```

```powershell
python -m pytest --cov=tksessentials --cov-fail-under=80
```

## 3) Local build (compile)

```powershell
python -m pip install build twine
python -m build
python -m twine check .\dist\*
```

Artifacts (`.whl` and `.tar.gz`) are written to `dist/`.

## 4) Release process

There are two release options:

### A) Automatic release via GitHub Actions (recommended)

1. Ensure your changes are merged to `main`.
2. CI will run tests, security scan, package build, and `bumpver` patch bump automatically in the `pypi-publish` stage.
3. If successful, CI publishes to PyPI.

### B) Manual release (local, when needed)

Use this only when you need a controlled local release artifact:

```powershell
bumpver update --patch
python -m build
python -m twine check .\dist\*
python -m twine upload .\dist\*
```

You must have PyPI credentials configured on your machine for the `twine upload` step.

## 5) Common maintenance actions

To clean the environment:

```powershell
pip3 freeze > to-uninstall.txt
pip3 uninstall -y -r to-uninstall.txt
```

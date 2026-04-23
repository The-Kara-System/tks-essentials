# Data Models Reference

`tksessentials.data_models` is the productive model package for the event-driven trading domain.
It keeps business nouns, event facts, and read-side snapshots separate so the lifecycle stays explicit from local strategy intent to a fully closed trade.

## Package Layout

```text
tksessentials.data_models
├── market_data/
│   ├── value_objects.py  # shared market-data enums
│   ├── payloads.py       # shared market-data request and envelope models
│   └── __init__.py       # shared market-data public API
├── value_objects.py   # enums and tiny reusable structs
├── payloads.py        # write-side business nouns
├── events.py          # immutable domain facts
└── snapshots.py       # read-side projections
```

## Modeling Rules

1. Payloads are nouns.
   Examples: `TradingSignalIntent`, `TradingSignal`, `OrderRequest`, `OrderFill`, `Trade`.
2. Events are past-tense facts.
   Examples: `TradingSignalIntentGranted`, `TradingSignalCreated`, `OrderPlaced`, `TradeClosed`.
3. Snapshots are query-side summaries.
   They are useful for APIs and dashboards, but not the write-side source of truth.
4. Strategy-local intent is not the same as transport-ready signal.
   `TradingSignalIntent` stays inside the strategy pod until PRM grants it.
5. A trade is not a signal and not an order.
   A trade is the aggregate built from execution outcomes.

## Trading Lifecycle

```text
 +----------------------------+
 | TradingSignalIntent        |
 | local, pre-PRM             |
 +-------------+--------------+
               |
               +--> TradingSignalIntentRejected --------------> terminal inside pod
               |
               +--> TradingSignalIntentCanceled --------------> terminal inside pod
               |
               +--> TradingSignalIntentExpired ---------------> terminal inside pod
               |
               +--> TradingSignalIntentGranted
                         |
                         v
                 +------------------------+
                 | TradingSignal          |
                 | PRM-granted, Kafka     |
                 +-----------+------------+
                             |
                             +--> TradingSignalInvalidated -----> terminal
                             |
                             +--> TradingSignalRejected --------> terminal
                             |
                             +--> TradingSignalQualifiedCold ---> valid but intentionally non-live
                             |
                             +--> TradingSignalQualifiedHot
                                        |
                                        v
                                 +--------------+
                                 | OrderRequest |
                                 +------+-------+
                                        |
                       +----------------+----------------+
                       |                                 |
                       v                                 v
                 OrderRejected                     OrderPlaced
                                                         |
                                  +----------------------+----------------------+
                                  |                                             |
                                  v                                             v
                            OrderCanceled                            OrderPartiallyFilled / OrderFilled
                                                                                  |
                                                                                  v
                                                                            +-----------+
                                                                            | OrderFill |
                                                                            +-----+-----+
                                                                                  |
                                                                                  v
                                                                               +------+
                                                                               | Trade |
                                                                               +--+---+
                                                                                  |
                                   +-------------------------+--------------------+-------------------+
                                   |                         |                                        |
                                   v                         v                                        v
                              TradeOpened              TradeIncreased                           TradeReduced
                                                                                                    |
                                                                                                    v
                                                                                               TradeClosed
                                                                                                    |
                                                                                                    v
                                                                                              ProfitRealized
```

## Lifecycle Vocabulary

| Term | Model | Meaning | What it is not |
| --- | --- | --- | --- |
| Trading signal intent | `TradingSignalIntent` | Local strategy-side draft that expresses the desire to publish a signal if PRM permits it. | Not yet a Kafka message, not an order, not a trade. |
| Trading signal | `TradingSignal` | PRM-granted transport payload that may leave the strategy pod. | Not a venue order and not merely a local draft anymore. |
| Order request | `OrderRequest` | One concrete execution instruction for a venue or bridge. | Not a fill and not the whole trade lifecycle. |
| Fill | `OrderFill` | One matched execution result from the venue. | Not the order request and not the trade aggregate. |
| Trade | `Trade` | Aggregate of actual exposure, state, and realized outcome. | Not the same as the originating signal and not one single order. |
| Event | `DomainEvent` and subclasses | Immutable fact that something happened. | Not current state and not the business noun itself. |
| Snapshot | `*Snapshot` classes | Query-side summary of latest known state. | Not the source of truth and not meant as the main event contract. |

## Value Objects

| Model | Purpose | Important members | Process role | Not the same as |
| --- | --- | --- | --- | --- |
| `Direction` | Describe exposure bias. | `LONG`, `SHORT` | Used by intents, signals, and trades. | Not execution side. |
| `Side` | Describe the concrete buy or sell action. | `BUY`, `SELL` | Used by intents, signals, orders, and fills. | Not directional bias. |
| `OrderType` | Describe venue order style. | `LIMIT`, `MARKET` | Used before or during order creation. | Not an order event. |
| `AggregateType` | Label which aggregate an event belongs to. | `SIGNAL`, `INTENT`, `ORDER`, `TRADE` | Used on `DomainEvent`. | Not business status. |
| `SignalStatus` | Snapshot status for a trading signal. | `INVALIDATED`, `CREATED`, `REJECTED`, `QUALIFIED_COLD`, `QUALIFIED_HOT` | Used on `TradingSignalSnapshot`. | Not an event. |
| `IntentStatus` | Snapshot status for a trading-signal intent. | `CREATED`, `GRANTED`, `REJECTED`, `CANCELED`, `EXPIRED` | Used on `TradingSignalIntentSnapshot`. | Not PRM logic itself. |
| `OrderStatus` | Snapshot status for an order. | `REQUESTED`, `PLACED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REJECTED` | Used on `OrderSnapshot`. | Not venue payload. |
| `TradeStatus` | Snapshot or payload status for a trade. | `PENDING`, `OPEN`, `PARTIALLY_CLOSED`, `CLOSED`, `CANCELED` | Used on `Trade` and `TradeSnapshot`. | Not one order result. |
| `LiquidityType` | Describe maker or taker role on fills. | `MAKER`, `TAKER`, `UNKNOWN` | Used on `OrderFill`. | Not order intent. |
| `SignalProvider` | Identify the signal provider contract owner. | `signal_provider_id`, `signal_provider_name` | Embedded in intents and signals. Defaults to `TKS`. | Not event `source` and not strategy identity. |
| `TradingSignalRejectionReason` | Structured reasons for rejecting a published signal. | Examples: `INVALID_DATA`, `INVALID_PRICE`, `MARKET_NOT_ALLOWED` | Used on `TradingSignalRejected`. | Not cold-routing reasons. |
| `TradingSignalColdReason` | Structured reasons for forcing a signal to stay cold. | Examples: `SYSTEM_IS_COLD`, `SIGNAL_MARKED_COLD`, `STRATEGY_NOT_QUALIFIED` | Used on `TradingSignalQualifiedCold`. | Not a hard rejection. |
| `TradingSignalIntentRejectionReason` | Structured reasons for rejecting a local intent before publication. | Examples: `STRATEGY_PRM_REJECTED`, `PRM_REJECTED`, `UNKNOWN_STRATEGY` | Used on `TradingSignalIntentRejected`. | Not the entire intent status. |

## Payload Models

| Model | Purpose | Key fields | Typical producer | Typical next step | Not the same as |
| --- | --- | --- | --- | --- | --- |
| `PayloadModel` | Strict base class for business nouns. | `extra="forbid"` config | Internal package base. | Subclassed by payload models. | Not a domain object by itself. |
| `TradingSignalIntent` | Local pre-PRM trading proposal. | `intent_id`, `signal_provider`, `signal_provider_signal_id`, `signal_provider_trade_id`, `strategy_id`, `market`, `side`, `direction`, `order_type`, `target_price`, `take_profit`, `stop_loss`, `size_pct`, `is_hot`, `created_at`, `valid_until`, `rationale`, `metadata` | Strategy pod. | Grant, reject, cancel, or expire. | Not yet the Kafka trading signal. |
| `TradingSignalIntentSpot` | Spot-specific local intent. | Inherits `TradingSignalIntent`, enforces `direction=LONG` | Spot strategy pod. | Grant to `TradingSignalSpot`. | Not a futures intent. |
| `TradingSignalIntentFuture` | Futures-specific local intent. | Same shape as `TradingSignalIntent` with long or short allowed | Futures strategy pod. | Grant to `TradingSignalFuture` or `TradingSignal`. | Not spot-only. |
| `TradingSignal` | PRM-granted transport signal. | All relevant intent fields plus `signal_id`, `prm_granted_at` | Strategy pod after PRM approval. | Kafka publication and downstream signal events. | Not just a local wish and not an order. |
| `TradingSignalSpot` | Spot-specific transport signal. | Same as `TradingSignal`, enforces `direction=LONG` | Spot strategy pod. | Spot bridge consumption. | Not a futures signal. |
| `TradingSignalFuture` | Futures-specific transport signal. | Same as `TradingSignal` with long or short allowed | Futures strategy pod. | Futures bridge consumption. | Not spot-only. |
| `OrderRequest` | One concrete venue instruction. | `order_id`, `intent_id`, `trade_id`, `market`, `side`, `order_type`, `quantity`, `limit_price`, `time_in_force`, `venue`, `reduce_only`, `created_at`, `metadata` | Bridge or execution router. | Place, reject, cancel, or fill. | Not a fill and not the trade aggregate. |
| `OrderFill` | One matched execution fact. | `fill_id`, `order_id`, `trade_id`, `market`, `side`, `filled_qty`, `filled_price`, `fee`, `liquidity`, `filled_at`, `metadata` | Venue adapter or broker bridge. | Trade update events. | Not the order instruction itself. |
| `Trade` | Aggregate of real exposure and outcome. | `trade_id`, `signal_id`, `signal_provider_trade_id`, `market`, `direction`, `status`, `opened_at`, `closed_at`, `entry_qty`, `exit_qty`, `avg_entry_price`, `avg_exit_price`, `realized_pnl`, `metadata` | Trade aggregate or portfolio service. | Open, increase, reduce, close, cancel, report PnL. | Not the originating signal and not one order. |

### Payload Helper Behavior

| Model | Helper | Meaning |
| --- | --- | --- |
| `TradingSignalIntent` | `is_exit_signal` | Returns `True` when the intent is sell-side and therefore reduces or closes exposure. |
| `TradingSignalIntent` | `can_expire(at_ms)` | Checks whether the intent should be treated as expired at a given timestamp. |
| `TradingSignalIntent` | `grant(signal_id, prm_granted_at)` | Materializes the intent into a `TradingSignal`. |
| `TradingSignalIntentSpot` | `grant(signal_id, prm_granted_at)` | Materializes a spot intent into a `TradingSignalSpot`. |
| `OrderRequest` | `is_limit_order` | Returns `True` when the order should be routed as a limit order. |
| `Trade` | `net_qty` | Remaining open quantity after subtracting exits from entries. |
| `Trade` | `is_closed` | `True` only when `status == CLOSED`. |

## Event Models

| Model | Purpose | Key fields | Producer | Next step | Not the same as |
| --- | --- | --- | --- | --- | --- |
| `EventModel` | Strict base class for event shapes. | `extra="forbid"` config | Internal package base. | Subclassed by event models. | Not a fact by itself. |
| `DomainEvent` | Shared envelope for all facts. | `event_id`, `event_type`, `occurred_at`, `aggregate_type`, `aggregate_id`, `correlation_id`, `causation_id`, `source`, `payload_version`, `metadata`, `payload` | Any event producer. | Routed, stored, projected. | Not the business noun itself. |
| `TradingSignalEvent` | Abstract base for signal facts. | `aggregate_type=SIGNAL`, `payload: TradingSignal` | Signal-producing services. | Concrete signal events. | Not intent or trade events. |
| `TradingSignalIntentEvent` | Abstract base for local intent facts. | `aggregate_type=INTENT`, `payload: TradingSignalIntent` | Strategy pod or PRM. | Concrete intent events. | Not published signal facts. |
| `OrderEvent` | Abstract base for order facts. | `aggregate_type=ORDER`, `payload: OrderRequest` | Execution layer. | Concrete order events. | Not fills or trades. |
| `FillEvent` | Abstract base for fill facts. | `aggregate_type=ORDER`, `payload: OrderFill` | Venue adapter. | Trade updates. | Not order requests. |
| `TradeEvent` | Abstract base for trade facts. | `aggregate_type=TRADE`, `payload: Trade` | Trade aggregate. | Concrete trade events. | Not the signal or order layers. |
| `TradingSignalInvalidated` | Raw or malformed signal data could not become a valid `TradingSignal`. | `reason`, raw `payload` dict | Validation edge. | Stop. | Not a valid signal. |
| `TradingSignalCreated` | A PRM-granted signal was materialized or published for downstream handling. | signal `payload` | Strategy pod or publishing service. | Qualification or stop. | Not the intent-creation fact. |
| `TradingSignalRejected` | A published signal was hard-stopped. | `reasons: list[TradingSignalRejectionReason]` | Bridge or routing service. | Stop. | Not cold qualification. |
| `TradingSignalQualifiedCold` | A signal remains valid but must stay cold. | `reasons: list[TradingSignalColdReason]` | Bridge or routing service. | Cold-only workflows. | Not a rejection. |
| `TradingSignalQualifiedHot` | A signal is eligible to continue toward live execution. | signal `payload` | Bridge or routing service. | Build `OrderRequest`. | Not an order yet. |
| `TradingSignalIntentCreated` | The strategy created a local intent. | intent `payload` | Strategy pod. | Grant, reject, cancel, expire. | Not publication. |
| `TradingSignalIntentGranted` | PRM granted the intent and linked it to a `signal_id`. | intent `payload`, `signal_id`, `prm_granted_at` | PRM or strategy pod. | Publish `TradingSignal`. | Not the final signal payload itself. |
| `TradingSignalIntentRejected` | PRM or policy rejected the local intent. | `reasons: list[TradingSignalIntentRejectionReason]`, `reason_detail` | PRM or strategy pod. | Stop. | Not a published signal rejection. |
| `TradingSignalIntentCanceled` | The local intent was deliberately withdrawn. | optional `reason` | Strategy pod. | Stop. | Not expiration. |
| `TradingSignalIntentExpired` | The local intent became stale before execution could continue. | optional `reason` | Strategy pod or scheduler. | Stop. | Not an explicit rejection. |
| `OrderRequested` | The system produced an order instruction. | order `payload` | Bridge or router. | Venue submission. | Not venue acknowledgement. |
| `OrderPlaced` | The venue acknowledged or accepted the order. | `venue_order_id` plus order `payload` | Execution adapter. | Fill, cancel, reject. | Not proof of fill. |
| `OrderRejected` | The order was rejected. | `reason` plus order `payload` | Execution adapter. | Stop or re-plan. | Not trade cancellation. |
| `OrderPartiallyFilled` | The order filled partially and remains open. | fill `payload` | Execution adapter. | More fills or cancel. | Not full fill. |
| `OrderFilled` | The order reached a fully filled state. | fill `payload` | Execution adapter. | Trade open/update/close. | Not the full trade lifecycle. |
| `OrderCanceled` | The order stopped before complete execution. | optional `reason` plus order `payload` | Execution adapter. | Stop or retry. | Not necessarily trade cancellation. |
| `TradeOpened` | A new trade aggregate was opened. | trade `payload` | Trade aggregate. | Increase, reduce, close. | Not the same as first signal publication. |
| `TradeIncreased` | Existing exposure increased. | trade `payload` | Trade aggregate. | More execution or close. | Not a new trade necessarily. |
| `TradeReduced` | Existing exposure decreased. | trade `payload` | Trade aggregate. | Further reduction or close. | Not necessarily terminal. |
| `TradeClosed` | The trade reached its normal closed state. | trade `payload` | Trade aggregate. | Realized reporting. | Not an order fill itself. |
| `TradeCanceled` | The trade lifecycle was aborted. | optional `reason` plus trade `payload` | Trade aggregate or policy layer. | Stop. | Not one order cancellation. |
| `ProfitRealized` | Profit was realized on the trade. | `realized_pnl_delta` plus trade `payload` | Trade aggregate. | Reporting, analytics. | Not the trade aggregate itself. |

## Snapshot Models

| Model | Purpose | Key fields | Typical consumer | Not the same as |
| --- | --- | --- | --- | --- |
| `SnapshotModel` | Strict base class for read-side summaries. | `extra="forbid"` config | Internal package base. | Not a projection by itself. |
| `TradingSignalSnapshot` | Latest view of a signal aggregate. | `trading_signal`, `status`, `reasons`, `last_event_id`, `last_event_at` | APIs, dashboards, replay tooling. | Not the signal event stream. |
| `TradingSignalIntentSnapshot` | Latest view of an intent aggregate with traceability. | `trading_signal_intent`, `status`, `granted_at`, `granted_signal_id`, `rejection_reasons`, `reason_detail`, `last_event_id`, `last_event_at` | APIs, PRM audit, debugging. | Not the intent event stream. |
| `OrderSnapshot` | Latest view of order state and fill progress. | `order`, `status`, `filled_qty`, `avg_fill_price`, `rejection_reason`, `last_event_id`, `last_event_at` | Execution UI, operations, replay tooling. | Not the order event stream. |
| `TradeSnapshot` | Latest view of trade state and realized outcome. | `trade`, `status`, `open_order_ids`, `last_realized_pnl_delta`, `last_event_id`, `last_event_at` | Portfolio UI, analytics, reporting. | Not the trade event stream. |

### Snapshot Helper Properties

| Model | Helper | Meaning |
| --- | --- | --- |
| `TradingSignalSnapshot` | `is_terminal` | `True` once the signal is invalidated, rejected, cold-qualified, or hot-qualified. |
| `TradingSignalIntentSnapshot` | `is_active` | `True` only while the intent still sits in created state and may progress. |
| `OrderSnapshot` | `is_terminal` | `True` once the order is filled, canceled, or rejected. |
| `TradeSnapshot` | `is_terminal` | `True` once the trade is closed or canceled. |

## Recommended Future Extension

Trade monitoring is intentionally not modeled yet because the contract is still fluid.
When it becomes stable, the recommended additions are:

- `TradeMonitoringTick`
  A monitoring event for current mark price, unrealized PnL, and position metrics.
- `TradeMonitoringClosed`
  A terminal monitoring event with `closed_at` and a structured `close_reason`.

These should be added as explicit models in this package rather than pushed as untyped dict payloads.

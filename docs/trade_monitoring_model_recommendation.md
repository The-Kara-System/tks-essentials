# Trade Monitoring Model Recommendation

`tks-performance-validator` now emits monitoring updates and close events for monitored trading signals.
To keep event contracts explicit and reusable, add dedicated models to `tksessentials/models.py`.

## Proposed Models

1. `TradeMonitoringTick(Event)`
- `event_type = "trade_monitoring_tick"`
- Fields:
  - `internal_signal_id: str`
  - `provider_signal_id: str`
  - `provider_trade_id: str`
  - `strategy_id: str`
  - `market: str`
  - `symbol: str`
  - `entry_price: float`
  - `tp: float`
  - `sl: float`
  - `mark_price: float`
  - `pnl_abs_per_unit: float`
  - `pnl_pct: float`
  - `opened_at: int`
  - `last_price_time: int | None`

2. `TradeMonitoringClosed(TradeMonitoringTick)`
- `event_type = "trade_monitoring_closed"`
- Additional fields:
  - `closed_at: int`
  - `close_reason: str`  # e.g. `TP_REACHED` or `SL_REACHED`

## Why

- Avoid ad-hoc dict schemas across services.
- Reuse same payload contract for realtime and historical topics.
- Keep close-event semantics explicit for UI and analytics services.

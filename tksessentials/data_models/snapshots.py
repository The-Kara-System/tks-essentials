"""Read-side snapshots for the event-driven trading design."""

import time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .payloads import (
    OrderRequest,
    PositionMarkV1,
    Trade,
    TradingSignal,
    TradingSignalIntent,
)
from .value_objects import (
    IntentStatus,
    OrderStatus,
    SignalStatus,
    TradeStatus,
    TradingSignalIntentRejectionReason,
)


class SnapshotModel(BaseModel):
    """Strict base class for query-side projections.

    Purpose: provide materialized state that is easy to serve to APIs or UIs.
    Not: not the write-side source of truth and not an event envelope.
    """

    model_config = ConfigDict(extra="forbid")


class PositionsMarkSnapshotV1(SnapshotModel):
    """Full short-lived position valuations or their freshness heartbeat.

    `as_of` and `last_snapshot_as_of` are Unix epoch milliseconds. A snapshot
    fully replaces the account's previous mark set. A heartbeat only confirms
    freshness and references the most recent full snapshot.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    schema_version: Literal[1] = 1
    kind: Literal["snapshot", "heartbeat"]
    account_id: str
    as_of: int = Field(gt=0)
    positions: list[PositionMarkV1] = Field(default_factory=list)
    last_snapshot_as_of: Optional[int] = Field(default=None, gt=0)

    @field_validator("account_id")
    def validate_account_id(cls, value: str) -> str:
        """Reject an empty account identity."""

        if not value.strip():
            raise ValueError("account_id must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_message_shape(self) -> "PositionsMarkSnapshotV1":
        """Keep full snapshots and lightweight heartbeats unambiguous."""

        position_ids = [position.position_id for position in self.positions]
        if len(position_ids) != len(set(position_ids)):
            raise ValueError("position_id must be unique within a mark snapshot.")

        if self.kind == "snapshot":
            if self.last_snapshot_as_of is not None:
                raise ValueError("snapshot must not set last_snapshot_as_of.")
            return self

        if self.positions:
            raise ValueError("heartbeat must not contain positions.")
        if self.last_snapshot_as_of is None:
            raise ValueError("last_snapshot_as_of is required for a heartbeat.")
        if self.last_snapshot_as_of > self.as_of:
            raise ValueError("last_snapshot_as_of must not be later than as_of.")
        return self


class TradingSignalSnapshot(SnapshotModel):
    """Current read-side view of a trading-signal aggregate.

    Purpose: summarize the latest signal status and decision context.
    Not: not the signal event stream and not a tradeable intent.
    """

    trading_signal: TradingSignal
    status: SignalStatus
    reasons: list[str] = Field(default_factory=list)
    last_event_id: Optional[str] = None
    last_event_at: int = Field(default_factory=lambda: int(time.time() * 1000))

    @property
    def is_terminal(self) -> bool:
        """Return whether the signal is no longer expected to change routing state."""

        return self.status in {
            SignalStatus.INVALIDATED,
            SignalStatus.REJECTED,
            SignalStatus.QUALIFIED_COLD,
            SignalStatus.QUALIFIED_HOT,
        }


class TradingSignalIntentSnapshot(SnapshotModel):
    """Current read-side view of a trading-signal-intent aggregate.

    Purpose: summarize whether PRM accepted, rejected, canceled, or expired the intent.
    Traceability: keeps the grant outcome or rejection reasons together with the underlying intent.
    Not: not the intent payload itself and not an order.
    """

    trading_signal_intent: TradingSignalIntent
    status: IntentStatus
    granted_at: Optional[int] = None
    granted_signal_id: Optional[str] = None
    rejection_reasons: list[TradingSignalIntentRejectionReason] = Field(default_factory=list)
    reason_detail: Optional[str] = None
    last_event_id: Optional[str] = None
    last_event_at: int = Field(default_factory=lambda: int(time.time() * 1000))

    @property
    def is_active(self) -> bool:
        """Return whether the intent can still lead to order creation."""

        return self.status == IntentStatus.CREATED


class OrderSnapshot(SnapshotModel):
    """Current read-side view of an order aggregate.

    Purpose: summarize venue-facing order state and fill progress.
    Not: not the order event stream and not the trade aggregate.
    """

    order: OrderRequest
    status: OrderStatus
    filled_qty: float = Field(default=0.0, ge=0)
    avg_fill_price: Optional[float] = None
    rejection_reason: Optional[str] = None
    last_event_id: Optional[str] = None
    last_event_at: int = Field(default_factory=lambda: int(time.time() * 1000))

    @property
    def is_terminal(self) -> bool:
        """Return whether no more order status changes are expected."""

        return self.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
        }


class TradeSnapshot(SnapshotModel):
    """Current read-side view of a trade aggregate.

    Purpose: expose current exposure and terminal state for downstream consumers.
    Not: not the trade event stream and not an order or fill.
    """

    trade: Trade
    status: TradeStatus
    open_order_ids: list[str] = Field(default_factory=list)
    last_realized_pnl_delta: float = 0.0
    last_event_id: Optional[str] = None
    last_event_at: int = Field(default_factory=lambda: int(time.time() * 1000))

    @property
    def is_terminal(self) -> bool:
        """Return whether the trade reached a terminal state."""

        return self.status in {TradeStatus.CLOSED, TradeStatus.CANCELED}

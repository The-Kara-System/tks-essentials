"""Business payload models for the event-driven trading design."""

import time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .value_objects import (
    Direction,
    LiquidityType,
    OrderType,
    SignalProvider,
    Side,
    TradeStatus,
)


class PayloadModel(BaseModel):
    """Strict base class for domain payloads.

    Purpose: keep durable business nouns separate from event envelopes.
    Not: not a lifecycle fact and not a read-side projection.
    """

    model_config = ConfigDict(extra="forbid")


class TradingSignalIntent(PayloadModel):
    """Internal pre-PRM trading-signal draft.

    Purpose: capture the strategy's intention to emit a `TradingSignal` if PRM allows it to leave the strategy pod.
    Process: created inside the strategy before the trading signal is granted and published to Kafka.
    Traceability: whether this intent was granted, rejected, canceled, or expired is tracked by
    `TradingSignalIntent*` events and `TradingSignalIntentSnapshot`.
    Not: not yet a cross-service `TradingSignal`, not an order, and not a trade.
    """

    intent_id: str
    signal_provider: SignalProvider = Field(default_factory=SignalProvider)
    signal_provider_signal_id: Optional[str] = None
    signal_provider_trade_id: Optional[str] = None
    strategy_id: str
    market: str
    side: Side
    direction: Direction
    order_type: OrderType
    target_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    size_pct: float = Field(gt=0)
    is_hot: bool = False
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    valid_until: Optional[int] = None
    rationale: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "intent_id",
        "strategy_id",
        "market",
        "signal_provider_signal_id",
        "signal_provider_trade_id",
        "rationale",
    )
    def validate_non_empty_strings(cls, value: Optional[str]) -> Optional[str]:
        """Reject blank identifiers and blank market strings."""

        if value is not None and not value.strip():
            raise ValueError("This field must not be blank when provided.")
        return value

    @field_validator("target_price", "take_profit", "stop_loss")
    def validate_positive_optional_prices(cls, value: Optional[float]) -> Optional[float]:
        """Require positive prices when price targets are supplied."""

        if value is not None and value <= 0:
            raise ValueError("Prices must be positive when provided.")
        return value

    @field_validator("valid_until")
    def validate_valid_until(cls, value: Optional[int], info) -> Optional[int]:
        """Ensure expiration, when present, is not earlier than creation time."""

        if value is not None:
            created_at = info.data.get("created_at")
            if created_at is not None and value < created_at:
                raise ValueError("valid_until must be greater than or equal to created_at.")
        return value

    @property
    def is_exit_signal(self) -> bool:
        """Return whether the draft primarily reduces or closes exposure."""

        return self.side == Side.SELL

    def can_expire(self, at_ms: int) -> bool:
        """Return whether the intent should be considered expired at the given timestamp."""

        return self.valid_until is not None and at_ms >= self.valid_until

    def grant(self, *, signal_id: str, prm_granted_at: int) -> "TradingSignal":
        """Materialize this intent as a publishable trading signal after PRM approval."""

        return TradingSignal(
            signal_id=signal_id,
            prm_granted_at=prm_granted_at,
            **self.model_dump(),
        )


class TradingSignal(TradingSignalIntent):
    """PRM-granted trading signal ready for cross-service transport.

    Purpose: represent the signal that is allowed to leave the strategy pod and be published to Kafka for bridges.
    Process: created from a `TradingSignalIntent` once PRM grants the intent.
    Timing: `created_at` captures when the strategy formed the intent, while `prm_granted_at` captures when PRM
    allowed that intent to become a transport signal.
    Not: not merely an internal wish anymore, not an order, and not a trade.
    """

    signal_id: str
    prm_granted_at: int

    @field_validator("signal_id")
    def validate_signal_id(cls, value: str) -> str:
        """Reject blank signal identifiers."""

        if not value.strip():
            raise ValueError("signal_id must not be blank.")
        return value

    @field_validator("prm_granted_at")
    def validate_prm_granted_at(cls, value: int, info) -> int:
        """Ensure PRM grant time is not earlier than the original intent creation time."""

        created_at = info.data.get("created_at")
        if created_at is not None and value < created_at:
            raise ValueError("prm_granted_at must be greater than or equal to created_at.")
        return value


class OrderRequest(PayloadModel):
    """One concrete venue instruction derived from an intent.

    Purpose: represent the exact order the execution layer wants to place on a venue.
    Process: emitted after a granted trading signal is consumed and translated into venue-facing execution.
    Not: not an intent, not a fill, and not the whole trade lifecycle.
    """

    order_id: str
    intent_id: str
    trade_id: Optional[str] = None
    market: str
    side: Side
    order_type: OrderType
    quantity: float = Field(gt=0)
    limit_price: Optional[float] = None
    time_in_force: Optional[str] = None
    venue: Optional[str] = None
    reduce_only: bool = False
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("order_id", "intent_id", "trade_id", "market", "time_in_force", "venue")
    def validate_non_empty_strings(cls, value: Optional[str]) -> Optional[str]:
        """Reject blank identifiers and optional routing strings."""

        if value is not None and not value.strip():
            raise ValueError("This field must not be blank when provided.")
        return value

    @field_validator("limit_price")
    def validate_limit_price(cls, value: Optional[float], info) -> Optional[float]:
        """Require a positive limit price when limit-style execution is used."""

        if value is not None and value <= 0:
            raise ValueError("limit_price must be positive when provided.")
        return value

    @model_validator(mode="after")
    def validate_limit_order_requirements(self) -> "OrderRequest":
        """Require a limit price whenever the order is configured as a limit order."""

        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders.")
        return self

    @property
    def is_limit_order(self) -> bool:
        """Return whether this request should be routed as a limit order."""

        return self.order_type == OrderType.LIMIT


class TradingSignalIntentSpot(TradingSignalIntent):
    """Spot-specific trading-signal intent.

    Purpose: keep spot intents explicit and enforce long-only exposure before PRM evaluation.
    Process: used when the strategy pod targets a spot bridge rather than a futures bridge.
    Not: not a futures intent and not a granted transport signal.
    """

    direction: Direction = Direction.LONG

    @field_validator("direction")
    def enforce_long_only_direction(cls, value: Direction) -> Direction:
        """Reject spot intents that request short exposure."""

        if value != Direction.LONG:
            raise ValueError("Spot trading-signal intents only support LONG direction.")
        return value

    def grant(self, *, signal_id: str, prm_granted_at: int) -> "TradingSignalSpot":
        """Materialize this spot intent as a spot trading signal."""

        return TradingSignalSpot(
            signal_id=signal_id,
            prm_granted_at=prm_granted_at,
            **self.model_dump(),
        )


class TradingSignalIntentFuture(TradingSignalIntent):
    """Futures-specific trading-signal intent.

    Purpose: keep futures intents explicit while allowing long or short exposure before PRM evaluation.
    Process: used when the strategy pod targets a futures bridge.
    Not: not a spot-only intent and not a granted transport signal yet.
    """

    def grant(self, *, signal_id: str, prm_granted_at: int) -> "TradingSignalFuture":
        """Materialize this futures intent as a futures trading signal."""

        return TradingSignalFuture(
            signal_id=signal_id,
            prm_granted_at=prm_granted_at,
            **self.model_dump(),
        )


class TradingSignalSpot(TradingSignal):
    """Spot-specific trading signal.

    Purpose: represent a PRM-granted signal that must route to spot execution.
    Process: emitted after a `TradingSignalIntentSpot` is granted and published for a spot bridge.
    Not: not a futures signal and not an order or trade.
    """

    direction: Direction = Direction.LONG

    @field_validator("direction")
    def enforce_long_only_direction(cls, value: Direction) -> Direction:
        """Reject spot signals that request short exposure."""

        if value != Direction.LONG:
            raise ValueError("Spot trading signals only support LONG direction.")
        return value


class TradingSignalFuture(TradingSignal):
    """Futures-specific trading signal.

    Purpose: represent a PRM-granted signal that routes to futures execution.
    Process: emitted after a futures intent is granted and published for a futures bridge.
    Not: not a spot-only signal and not an order or trade.
    """


class OrderFill(PayloadModel):
    """Execution fact for matched liquidity.

    Purpose: record the actual quantity, price, and fee produced by a venue execution.
    Process: generated after an order is accepted by the venue and execution occurs.
    Not: not the order request and not the trade aggregate.
    """

    fill_id: str
    order_id: str
    trade_id: Optional[str] = None
    market: str
    side: Side
    filled_qty: float = Field(gt=0)
    filled_price: float = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)
    liquidity: LiquidityType = LiquidityType.UNKNOWN
    filled_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fill_id", "order_id", "trade_id", "market")
    def validate_non_empty_strings(cls, value: Optional[str]) -> Optional[str]:
        """Reject blank identifiers and blank market strings."""

        if value is not None and not value.strip():
            raise ValueError("This field must not be blank when provided.")
        return value


class Trade(PayloadModel):
    """Business aggregate for actual market exposure and realized outcome.

    Purpose: summarize the trade lifecycle built from one or more fills.
    Process: opened, increased, reduced, and closed by execution facts rather than by signals alone.
    Not: not the original signal, not one order, and not one fill.
    """

    trade_id: str
    signal_id: Optional[str] = None
    signal_provider_trade_id: Optional[str] = None
    market: str
    direction: Direction
    status: TradeStatus
    opened_at: Optional[int] = None
    closed_at: Optional[int] = None
    entry_qty: float = Field(default=0.0, ge=0)
    exit_qty: float = Field(default=0.0, ge=0)
    avg_entry_price: Optional[float] = None
    avg_exit_price: Optional[float] = None
    realized_pnl: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trade_id", "signal_id", "signal_provider_trade_id", "market")
    def validate_non_empty_strings(cls, value: Optional[str]) -> Optional[str]:
        """Reject blank identifiers and blank market strings."""

        if value is not None and not value.strip():
            raise ValueError("This field must not be blank when provided.")
        return value

    @field_validator("avg_entry_price", "avg_exit_price")
    def validate_positive_optional_prices(cls, value: Optional[float]) -> Optional[float]:
        """Ensure average prices are positive when present."""

        if value is not None and value <= 0:
            raise ValueError("Average prices must be positive when provided.")
        return value

    @property
    def net_qty(self) -> float:
        """Return the still-open quantity implied by entry and exit quantities."""

        return max(self.entry_qty - self.exit_qty, 0.0)

    @property
    def is_closed(self) -> bool:
        """Return whether the trade is already in a terminal closed state."""

        return self.status == TradeStatus.CLOSED

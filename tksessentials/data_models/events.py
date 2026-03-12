"""Event envelopes for the event-driven trading design."""

import time
from abc import ABC
from typing import Any, Optional, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .payloads import OrderFill, OrderRequest, Trade, TradingSignal, TradingSignalIntent
from .value_objects import (
    AggregateType,
    TradingSignalColdReason,
    TradingSignalIntentRejectionReason,
    TradingSignalRejectionReason,
)


class EventModel(BaseModel):
    """Strict base class for domain events.

    Purpose: keep emitted facts consistent and easy to route on an event bus.
    Not: not a business aggregate and not a read-side snapshot.
    """

    model_config = ConfigDict(extra="forbid")


class DomainEvent(EventModel):
    """Shared event envelope for all trading domain facts.

    Purpose: carry metadata such as correlation, causation, and aggregate identity around a concrete payload.
    Process: every concrete event in the trading flow should inherit from this envelope.
    Not: not the business payload itself; the `payload` field carries that meaning.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    occurred_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    aggregate_type: AggregateType
    aggregate_id: str
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    source: Optional[str] = None
    payload_version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload: Any

    @field_validator(
        "event_id",
        "event_type",
        "aggregate_id",
        "correlation_id",
        "causation_id",
        "source",
    )
    def validate_non_empty_strings(cls, value: Optional[str]) -> Optional[str]:
        """Reject blank identifiers and routing strings."""

        if value is not None and not value.strip():
            raise ValueError("This field must not be blank when provided.")
        return value

    @classmethod
    def new(
        cls,
        *,
        aggregate_id: str,
        payload: Any,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        **extra: Any,
    ) -> Self:
        """Create a new event with generated metadata and caller-supplied payload."""

        return cls(
            aggregate_id=aggregate_id,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source=source,
            metadata=metadata or {},
            **extra,
        )


class TradingSignalEvent(DomainEvent, ABC):
    """Base event for facts about the trading-signal aggregate."""

    aggregate_type: AggregateType = AggregateType.SIGNAL
    payload: TradingSignal


class TradingSignalIntentEvent(DomainEvent, ABC):
    """Base event for facts about the trading-signal-intent aggregate."""

    aggregate_type: AggregateType = AggregateType.INTENT
    payload: TradingSignalIntent


class OrderEvent(DomainEvent, ABC):
    """Base event for facts about the order aggregate."""

    aggregate_type: AggregateType = AggregateType.ORDER
    payload: OrderRequest


class FillEvent(DomainEvent, ABC):
    """Base event for facts about one order fill."""

    aggregate_type: AggregateType = AggregateType.ORDER
    payload: OrderFill


class TradeEvent(DomainEvent, ABC):
    """Base event for facts about the trade aggregate."""

    aggregate_type: AggregateType = AggregateType.TRADE
    payload: Trade


class TradingSignalInvalidated(DomainEvent):
    """Fact that raw trading-signal data could not become a valid signal.

    Purpose: preserve the invalid payload and why it was stopped.
    Not: not a valid signal and not a created tradeable decision.
    """

    event_type: str = "trading_signal_invalidated"
    aggregate_type: AggregateType = AggregateType.SIGNAL
    payload: dict[str, Any]
    reason: str


class TradingSignalCreated(TradingSignalEvent):
    """Fact that a PRM-granted trading signal was materialized for cross-service publication."""

    event_type: str = "trading_signal_created"


class TradingSignalRejected(TradingSignalEvent):
    """Fact that a published trading signal was rejected and will not proceed further."""

    event_type: str = "trading_signal_rejected"
    reasons: list[TradingSignalRejectionReason] = Field(default_factory=list)


class TradingSignalQualifiedCold(TradingSignalEvent):
    """Fact that a published trading signal remains valid but must stay cold."""

    event_type: str = "trading_signal_qualified_cold"
    reasons: list[TradingSignalColdReason] = Field(default_factory=list)


class TradingSignalQualifiedHot(TradingSignalEvent):
    """Fact that a created trading signal may proceed toward live execution intent."""

    event_type: str = "trading_signal_qualified_hot"


class TradingSignalIntentCreated(TradingSignalIntentEvent):
    """Fact that the strategy created a local trading-signal intent before PRM approval."""

    event_type: str = "trading_signal_intent_created"


class TradingSignalIntentGranted(TradingSignalIntentEvent):
    """Fact that PRM granted a local trading-signal intent and produced a transport signal."""

    event_type: str = "trading_signal_intent_granted"
    signal_id: str
    prm_granted_at: int

    @field_validator("signal_id")
    def validate_signal_id(cls, value: str) -> str:
        """Reject blank granted signal identifiers."""

        if not value.strip():
            raise ValueError("signal_id must not be blank.")
        return value


class TradingSignalIntentRejected(TradingSignalIntentEvent):
    """Fact that PRM or policy rejected a local trading-signal intent."""

    event_type: str = "trading_signal_intent_rejected"
    reasons: list[TradingSignalIntentRejectionReason] = Field(default_factory=list)
    reason_detail: Optional[str] = None


class TradingSignalIntentCanceled(TradingSignalIntentEvent):
    """Fact that a previously created trading-signal intent will no longer be executed."""

    event_type: str = "trading_signal_intent_canceled"
    reason: Optional[str] = None


class TradingSignalIntentExpired(TradingSignalIntentEvent):
    """Fact that a trading-signal intent expired before execution could continue."""

    event_type: str = "trading_signal_intent_expired"
    reason: Optional[str] = None


class OrderRequested(OrderEvent):
    """Fact that the system produced a venue-facing order request."""

    event_type: str = "order_requested"


class OrderPlaced(OrderEvent):
    """Fact that a venue accepted or acknowledged the order request."""

    event_type: str = "order_placed"
    venue_order_id: Optional[str] = None


class OrderRejected(OrderEvent):
    """Fact that the venue or execution layer rejected the requested order."""

    event_type: str = "order_rejected"
    reason: str


class OrderPartiallyFilled(FillEvent):
    """Fact that an order was partially filled but remains active."""

    event_type: str = "order_partially_filled"


class OrderFilled(FillEvent):
    """Fact that an order reached a fully filled state."""

    event_type: str = "order_filled"


class OrderCanceled(OrderEvent):
    """Fact that an order was canceled before full execution."""

    event_type: str = "order_canceled"
    reason: Optional[str] = None


class TradeOpened(TradeEvent):
    """Fact that execution opened a new trade aggregate."""

    event_type: str = "trade_opened"


class TradeIncreased(TradeEvent):
    """Fact that execution increased an already open trade."""

    event_type: str = "trade_increased"


class TradeReduced(TradeEvent):
    """Fact that execution reduced an already open trade."""

    event_type: str = "trade_reduced"


class TradeClosed(TradeEvent):
    """Fact that execution closed the trade aggregate."""

    event_type: str = "trade_closed"


class TradeCanceled(TradeEvent):
    """Fact that the trade lifecycle was aborted before a normal close."""

    event_type: str = "trade_canceled"
    reason: Optional[str] = None


class ProfitRealized(TradeEvent):
    """Fact that a trade realized profit.

    Purpose: expose the profit delta as a separate domain fact even though the trade payload also exists.
    Not: not an order fill and not the trade aggregate itself.
    """

    event_type: str = "profit_realized"
    realized_pnl_delta: float

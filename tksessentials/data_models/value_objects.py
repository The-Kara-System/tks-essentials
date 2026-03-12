"""Reusable value objects for the event-driven trading model set."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class Direction(str, Enum):
    """Directional bias for exposure.

    Purpose: describe whether the strategy wants long or short exposure.
    Not: not the same thing as buy or sell, which is execution side.
    """

    LONG = "long"
    SHORT = "short"


class Side(str, Enum):
    """Execution side for an instruction or fill.

    Purpose: express whether the action buys or sells an asset.
    Not: not the whole trade lifecycle and not the same as directional bias.
    """

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Venue order style.

    Purpose: describe how the execution layer should place an order.
    Not: not an event and not proof that the order was accepted by the venue.
    """

    LIMIT = "limit"
    MARKET = "market"


class AggregateType(str, Enum):
    """Aggregate families used by the event envelope.

    Purpose: label which business object an event belongs to.
    Not: not a status and not a payload model.
    """

    SIGNAL = "signal"
    INTENT = "intent"
    ORDER = "order"
    TRADE = "trade"


class SignalStatus(str, Enum):
    """Read-side status for a signal aggregate."""

    INVALIDATED = "invalidated"
    CREATED = "created"
    REJECTED = "rejected"
    QUALIFIED_COLD = "qualified_cold"
    QUALIFIED_HOT = "qualified_hot"


class IntentStatus(str, Enum):
    """Read-side status for an intent aggregate."""

    CREATED = "created"
    GRANTED = "granted"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    """Read-side status for an order aggregate."""

    REQUESTED = "requested"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class TradeStatus(str, Enum):
    """Read-side status for a trade aggregate."""

    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    CANCELED = "canceled"


class LiquidityType(str, Enum):
    """Liquidity role attached to a fill."""

    MAKER = "maker"
    TAKER = "taker"
    UNKNOWN = "unknown"


class ValueObject(BaseModel):
    """Strict base class for tiny reusable data structures.

    Purpose: keep shared value objects explicit and immutable-like.
    Not: not a domain aggregate and not an event envelope.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class SignalProvider(ValueObject):
    """Identity of the signal provider that owns or emits a signal.

    Purpose: make signal-provider identity explicit for cross-system trading contracts.
    Process: embedded in `TradingSignal` payloads and defaults to the local provider identity `TKS`.
    Not: not the emitting service of a domain event and not the strategy itself.
    """

    signal_provider_id: str = "tks"
    signal_provider_name: str = "TKS"

    @field_validator("signal_provider_id", "signal_provider_name")
    def validate_non_empty_strings(cls, value: str) -> str:
        """Reject blank signal-provider identifiers and names."""

        if not value.strip():
            raise ValueError("This field must not be blank.")
        return value


class TradingSignalRejectionReason(str, Enum):
    """Structured reasons explaining why a published trading signal was rejected.

    Purpose: preserve machine-readable stop reasons after a transport signal exists.
    Not: not the signal status itself and not a cold-routing reason.
    """

    PRM_REJECTED = "prm_rejected"
    NOT_AUTHENTICATED = "not_authenticated"
    SCAM = "scam"
    DOS_ATTACK = "dos_attack"
    BANNED_SIGNAL_PROVIDER = "banned_signal_provider"
    UNKNOWN_SIGNAL_PROVIDER = "unknown_signal_provider"
    BANNED_STRATEGY = "banned_strategy"
    UNKNOWN_STRATEGY = "unknown_strategy"
    DISQUALIFIED_STRATEGY = "disqualified_strategy"
    BANNED_IP = "banned_ip"
    MARKET_NOT_ALLOWED = "market_not_allowed"
    INVALID_DATA = "invalid_data"
    INVALID_PRICE = "invalid_price"
    INCOMPLETE = "incomplete"


class TradingSignalColdReason(str, Enum):
    """Structured reasons explaining why a published trading signal stays cold.

    Purpose: distinguish valid-but-non-executable signals from hard rejections.
    Not: not a signal rejection and not an order or trade status.
    """

    SIGNAL_MARKED_COLD = "signal_marked_cold"
    SYSTEM_IS_COLD = "system_is_cold"
    SIGNAL_PROVIDER_NOT_ELIGIBLE = "signal_provider_not_eligible"
    STRATEGY_NOT_QUALIFIED = "strategy_not_qualified"
    DISQUALIFIED_STRATEGY = "disqualified_strategy"


class TradingSignalIntentRejectionReason(str, Enum):
    """Structured reasons explaining why a trading-signal intent was denied.

    Purpose: preserve PRM and policy outcomes in a machine-readable form.
    Not: not an event by itself and not the full intent lifecycle state.
    """

    STRATEGY_PRM_REJECTED = "strategy_prm_rejected"
    PRM_REJECTED = "prm_rejected"
    NOT_AUTHENTICATED = "not_authenticated"
    SCAM = "scam"
    DOS_ATTACK = "dos_attack"
    BANNED_SIGNAL_PROVIDER = "banned_signal_provider"
    UNKNOWN_SIGNAL_PROVIDER = "unknown_signal_provider"
    BANNED_STRATEGY = "banned_strategy"
    UNKNOWN_STRATEGY = "unknown_strategy"
    DISQUALIFIED_STRATEGY = "disqualified_strategy"
    BANNED_IP = "banned_ip"
    MARKET_NOT_ALLOWED = "market_not_allowed"
    INVALID_DATA = "invalid_data"
    INVALID_PRICE = "invalid_price"
    INCOMPLETE = "incomplete"

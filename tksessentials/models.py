import time
from abc import ABC
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Dict, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT_ORDER = "limit_order"
    MARKET_ORDER = "market_order"


class Event(ABC, BaseModel):
    event_type: ClassVar[str]
    event_time: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        validation_alias=AliasChoices("event_time", "event_timestamp", "E"),
    )
    detail: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def serialize(self) -> Dict[str, Any]:
        payload = {
            "event_type": self.event_type,
            "detail": self.detail,
            "data": self._serialize_data(self.data),
        }
        return payload

    def _serialize_data(self, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if data is None:
            return None
        return {key: self._serialize_value(value) for key, value in data.items()}

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone().isoformat()
        if isinstance(value, dict):
            return self._serialize_data(value)
        return value

    @property
    def event_timestamp(self) -> int:
        return self.event_time


class TradingSignal(BaseModel):
    provider_signal_id: str = Field(
        ...,
        description="Mandatory. Provide us with your signal id. This correlation id is your own 'signal id' \
            of your internal system. Your and our party will use it to inspect process errors. \
            Do NOT mistaken this correlation id with the trade id.",
    )
    provider_trade_id: str = Field(
        ...,
        description="Mandatory. We describes a trade as a buy and a sell (not soley a buy OR a sell), \
            which has a unique provider_trade_id (the same for both, respectively all of them). \
            Every trade is expected to consist of at least one buy signal and at least one sell signal.\
            Both have a unique provider_signal_id, but - again - share the same provider_trade_id. \
            Thus, the provider_trade_id is mandatory for each signal sent. This will allow to create \
            a multi-position-trade. \
            \
            E.g. one can send one long signal with a provider_trade_id 77 and another long signal a \
            few hours later also with the provider_trade_id 77. Still, both signals require their \
            unique provider_signal_id. Provided that the position_size_in_percentage is less than \
            100 on the first one. \
            All updates provided by Freya Alpha will hold the provider_trade_id and likely the provider_signal_id \
            - if it concerns a signal itself.",
    )
    provider_id: str = Field(
        ..., description="Mandatory. Your ID as a provider, who emitted the signal."
    )
    strategy_id: str = Field(
        ...,
        description="Mandatory. Provide the id of the strategy (you might have more than one algorithm), which is sending a signal.",
    )
    is_hot_signal: bool = Field(
        default=False,
        description="Mandatory. By DEFAULT, every signal is marked as a COLD SIGNAL. \
            That is a paper-trading signal and will only be processed for forward-performance \
            testing. Hot signals are suggested to be processed by the order engines - \
            provided all other requirements for hot trading are fulfilled. Set this \
            value to true to suggest a hot trade.",
    )
    market: str = Field(
        ..., description="Mandatory. The market you want to trade. e.g. BTC/USDT"
    )
    data_source: str = Field(
        ...,
        description="Mandatory. The source of data you based your decision on. E.g. Binance, CoinMarketCap,\
            Chainlink, etc. This is to safeguard investments, which base on manipulated data sources.",
    )
    direction: Direction = Field(
        default=Direction.LONG,
        description="Mandatory. Trading direction for the signal.",
    )
    side: Side = Field(
        ..., description="Mandatory. Simply BUY (open trade) or SELL (close trade)."
    )
    order_type: OrderType = Field(
        default=OrderType.LIMIT_ORDER,
        description="Mandatory. Default is Limit Order. Please be careful with Markets Orders as slipage could be high.",
    )
    price: float = Field(
        ...,
        description="Mandatory. The price to buy or sell. Used for the limit-order. If market-order is set, this price is a reference price only to avoid average slipage greater than 10%.",
    )
    tp: float = Field(
        ...,
        description="Mandatory. Take-profit in an absolute price. In case of a sell signal (limit order) the TP must equal the price.",
    )
    sl: float = Field(
        ...,
        description="Mandatory. Stop-loss in an absolute price. In case of a sell signal (limit order) the SL must equal the price.",
    )
    position_size_in_percentage: float = Field(
        default=100,
        description="Caution, if one chooses another value than 100, the system will create a multi-position-trade (for scaling-in and scaling-out on a trade). In addition, one has to provide a provider_trade_id in order for the system to create a multi-position-trade. Any consecutive trades (scale-in/out), need to have provide the same provider_trade_id. Percentage of the trade position this algortihm is allowed to trade. Default is 100%, which is 1 position of your fund's positions. Another number than 100, will assume this trade has multiple positions. If a signal provider has one partial position open and then closes it, it will also regard the trade as fully closed.",
    )
    date_of_creation: int = Field(
        description="Mandatory. The UTC POSIX date/time when the signal was created in the signal provider's system. Use the POSIX UTC date format."
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_validator(
        "provider_id",
        "strategy_id",
        "provider_signal_id",
        "provider_trade_id",
        "market",
        "data_source",
    )
    def check_string_not_empty(cls, v):
        if not v or v.isspace():
            raise ValueError("This field must not be empty.")
        return v

    @field_validator("price", "tp", "sl", "position_size_in_percentage")
    def check_positive_value(cls, v):
        if v <= 0:
            raise ValueError("price must a positive number.")
        return v

    @field_validator("is_hot_signal")
    def check_boolean(cls, v):
        if not isinstance(v, bool):
            raise ValueError("is_hot_signal must be a boolean.")
        return v

    @field_validator("direction", mode="before")
    def normalize_direction(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("side", mode="before")
    def normalize_side(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("order_type", mode="before")
    def normalize_order_type(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("date_of_creation")
    def check_datetime(cls, v):
        if not isinstance(v, int):
            raise ValueError(
                f"date_of_creation must be an integer representing a POSIX timestamp in milliseconds, got type {type(v).__name__}"
            )
        return v


class TradingSignalSpot(TradingSignal):
    direction: Direction = Field(
        default=Direction.LONG,
        description="Mandatory. For Spot trading this must be LONG.",
    )

    @field_validator("direction")
    def enforce_long_only(cls, v):
        if v != Direction.LONG:
            raise ValueError("Only LONG direction is supported for spot trading.")
        return v


class TradingSignalFuture(TradingSignal):
    direction: Direction = Field(
        default=Direction.LONG,
        description="Mandatory. For Futures, LONG and SHORT are both supported.",
    )


class TradingSignalDataInvalidated(Event):
    signal_data: str
    ip: str
    event_type: ClassVar[str] = "trading_signal_data_invalidated"
    reason_for_invalidation: str


class TradingSignalIncoming(Event):
    signal_data: Dict
    ip: str
    event_type: ClassVar[str] = "trading_signal_incoming"


class TradingSignalEvent(Event, ABC):
    trading_signal: TradingSignal


class TradingSignalReceived(TradingSignalEvent):
    internal_signal_id: str
    event_type: ClassVar[str] = "trading_signal_received"
    ip: str
    date_of_reception: int = Field(default_factory=lambda: int(time.time() * 1000))


class ReasonForRejection(str, Enum):
    STRATEGY_PRM_REJECTED = "strategy_prm_rejected"
    PRM_REJECTED = "prm_rejected"
    NOT_AUTHENTICATED = "not_authenticated"
    SCAM = "scam"
    DOS_ATTACK = "dos_attack"
    BANNED_PROVIDER = "banned_provider"
    UKNOWN_PROVIDER = "unknown_provider"
    BANNED_STRATEGY = "banned_strategy"
    UNKNOWN_STRATEGY = "unknown_strategy"
    DISQUALIFIED_STRATEGY = "disqualified strategy"
    BANNED_IP = "banned_ip"
    MARKET_NOT_ALLOWED = "market_not_allowed"
    INVALID_DATA = "invalid_data"
    INVALID_PRICE = "invalid_price"
    INCLOMPLETE = "incomplete"


class TradingSignalRejected(TradingSignalReceived):
    reasons_for_rejection: set[ReasonForRejection]
    event_type: ClassVar[str] = "trading_signal_rejected"
    date_of_rejection: int = Field(default_factory=lambda: int(time.time() * 1000))

    @classmethod
    def from_raw_signal(
        cls,
        raw_signal: TradingSignalReceived,
        reasons_for_rejection: ReasonForRejection,
    ):
        rejected_signal = cls(
            **raw_signal.model_dump(), reasons_for_rejection=reasons_for_rejection
        )
        return rejected_signal


class ReasonForCold(str, Enum):
    PROVIDER_NOT_ELIGABLE_FOR_HOT_SIGNAL = "provider_not_eligable_for_hot_signal"
    STRATEGY_NOT_QUALIFIED = "strategy_not_qualified"
    DISQUALIFIED_STRATEGY = "disqualified_strategy"
    SYSTEM_IS_COLD = "system_is_cold"
    SIGNAL_MARKED_COLD = "signal_marked_cold"


class TradingSignalQualified(TradingSignalReceived, ABC):
    event_type: ClassVar[str] = "trading_signal_qualified"
    date_of_qualification: int = Field(default_factory=lambda: int(time.time() * 1000))

    def __init__(self, **data):
        if "time_of_qualification" in data:
            data["time_of_qualification"] = data["time_of_qualification"].astimezone(
                tz=timezone.utc
            )
        super().__init__(**data)


class TradingSignalQualifiedHot(TradingSignalQualified):
    event_type: ClassVar[str] = "trading_signal_qualified_hot"


class TradingSignalQualifiedCold(TradingSignalQualified):
    event_type: ClassVar[str] = "trading_signal_qualified_cold"
    reasons_for_cold: set[ReasonForCold]


class TradeCreated(Event):
    trade_id: str
    event_type: ClassVar[str] = "trade_created"


class TradeCanceled(Event):
    trade_id: str
    reason: str
    event_type: ClassVar[str] = "trade_canceled"


class TradeFinished(Event):
    trade_id: str
    event_type: ClassVar[str] = "trade_finished"


class OrderCreated(Event):
    order_id: str
    event_type: ClassVar[str] = "order_created"


class OrderFilled(Event):
    order_id: str
    event_type: ClassVar[str] = "order_filled"


class OrderCanceled(Event):
    order_id: str
    reason: Optional[str] = None
    event_type: ClassVar[str] = "order_canceled"


class ProfitTaken(Event):
    trade_id: str
    profit_amount: float
    event_type: ClassVar[str] = "profit_taken"

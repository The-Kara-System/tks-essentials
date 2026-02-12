from datetime import datetime, timezone
from typing import ClassVar

import pytest
from pydantic import ValidationError

from tksessentials.models import (
    Direction,
    Event,
    OrderType,
    ReasonForCold,
    ReasonForRejection,
    Side,
    TradingSignal,
    TradingSignalFuture,
    TradingSignalQualifiedCold,
    TradingSignalReceived,
    TradingSignalRejected,
    TradingSignalSpot,
)


def _valid_signal_payload() -> dict:
    return {
        "provider_signal_id": "sig-1",
        "provider_trade_id": "trade-1",
        "provider_id": "provider-a",
        "strategy_id": "strategy-a",
        "is_hot_signal": False,
        "market": "BTC/USDT",
        "data_source": "Binance",
        "direction": "long",
        "side": "buy",
        "order_type": "limit_order",
        "price": 100.0,
        "tp": 110.0,
        "sl": 95.0,
        "position_size_in_percentage": 100.0,
        "date_of_creation": 1735689600000,
    }


def test_trading_signal_accepts_valid_payload():
    signal = TradingSignal(**_valid_signal_payload())

    assert signal.provider_signal_id == "sig-1"
    assert signal.direction == "long"
    assert signal.side == "buy"
    assert signal.order_type == "limit_order"


@pytest.mark.parametrize(
    "direction, side, order_type",
    [
        ("LONG", "BUY", "LIMIT_ORDER"),
        ("long", "sell", "market_order"),
    ],
)
def test_trading_signal_normalizes_enum_like_inputs(direction, side, order_type):
    payload = _valid_signal_payload()
    payload.update({"direction": direction, "side": side, "order_type": order_type})

    signal = TradingSignal(**payload)

    assert signal.direction in {"long", "short"}
    assert signal.side in {"buy", "sell"}
    assert signal.order_type in {"limit_order", "market_order"}


@pytest.mark.parametrize(
    "field_name",
    [
        "provider_id",
        "strategy_id",
        "provider_signal_id",
        "provider_trade_id",
        "market",
        "data_source",
    ],
)
def test_trading_signal_rejects_empty_required_strings(field_name):
    payload = _valid_signal_payload()
    payload[field_name] = "   "

    with pytest.raises(ValidationError):
        TradingSignal(**payload)


@pytest.mark.parametrize("field_name", ["price", "tp", "sl", "position_size_in_percentage"])
def test_trading_signal_rejects_non_positive_numbers(field_name):
    payload = _valid_signal_payload()
    payload[field_name] = 0

    with pytest.raises(ValidationError):
        TradingSignal(**payload)


def test_trading_signal_rejects_non_integer_date_of_creation():
    payload = _valid_signal_payload()
    payload["date_of_creation"] = "not-an-int"

    with pytest.raises(ValidationError):
        TradingSignal(**payload)


def test_trading_signal_spot_rejects_short_direction():
    payload = _valid_signal_payload()
    payload["direction"] = "short"

    with pytest.raises(ValidationError):
        TradingSignalSpot(**payload)


def test_trading_signal_future_accepts_short_direction():
    payload = _valid_signal_payload()
    payload["direction"] = "short"

    signal = TradingSignalFuture(**payload)
    assert signal.direction == "short"


def test_trading_signal_model_dump_uses_enum_values():
    payload = _valid_signal_payload()
    payload["direction"] = Direction.SHORT
    payload["side"] = Side.SELL
    payload["order_type"] = OrderType.MARKET_ORDER

    signal = TradingSignal(**payload)
    dumped = signal.model_dump()

    assert dumped["direction"] == "short"
    assert dumped["side"] == "sell"
    assert dumped["order_type"] == "market_order"


class DummyEvent(Event):
    event_type: ClassVar[str] = "dummy_event"


def test_event_serialize_handles_datetime_and_nested_dict():
    now = datetime.now(tz=timezone.utc)
    event = DummyEvent(
        detail="test",
        data={
            "created_at": now,
            "nested": {"updated_at": now},
            "raw": 123,
        },
    )

    payload = event.serialize()

    assert payload["event_type"] == "dummy_event"
    assert payload["detail"] == "test"
    assert isinstance(payload["data"]["created_at"], str)
    assert "T" in payload["data"]["created_at"]
    assert isinstance(payload["data"]["nested"]["updated_at"], str)
    assert payload["data"]["raw"] == 123


def test_event_timestamp_aliases_and_property():
    event_with_alias = DummyEvent(event_timestamp=111)
    event_with_short_alias = DummyEvent(E=222)

    assert event_with_alias.event_time == 111
    assert event_with_alias.event_timestamp == 111
    assert event_with_short_alias.event_time == 222
    assert event_with_short_alias.event_timestamp == 222


def test_trading_signal_received_defaults_date_of_reception():
    received = TradingSignalReceived(
        trading_signal=TradingSignal(**_valid_signal_payload()),
        internal_signal_id="internal-1",
        ip="127.0.0.1",
    )

    assert isinstance(received.date_of_reception, int)
    assert received.event_type == "trading_signal_received"


def test_trading_signal_rejected_from_raw_signal():
    raw_signal = TradingSignalReceived(
        trading_signal=TradingSignal(**_valid_signal_payload()),
        internal_signal_id="internal-1",
        ip="127.0.0.1",
    )

    rejected = TradingSignalRejected.from_raw_signal(
        raw_signal=raw_signal,
        reasons_for_rejection={ReasonForRejection.INVALID_DATA},
    )

    assert rejected.internal_signal_id == raw_signal.internal_signal_id
    assert rejected.trading_signal.provider_signal_id == "sig-1"
    assert rejected.reasons_for_rejection == {ReasonForRejection.INVALID_DATA}
    assert rejected.event_type == "trading_signal_rejected"


def test_trading_signal_qualified_cold_requires_reasons():
    with pytest.raises(ValidationError):
        TradingSignalQualifiedCold(
            trading_signal=TradingSignal(**_valid_signal_payload()),
            internal_signal_id="internal-1",
            ip="127.0.0.1",
        )


def test_trading_signal_qualified_cold_accepts_reasons_set():
    qualified = TradingSignalQualifiedCold(
        trading_signal=TradingSignal(**_valid_signal_payload()),
        internal_signal_id="internal-1",
        ip="127.0.0.1",
        reasons_for_cold={ReasonForCold.SYSTEM_IS_COLD},
    )

    assert qualified.reasons_for_cold == {ReasonForCold.SYSTEM_IS_COLD}
    assert qualified.event_type == "trading_signal_qualified_cold"

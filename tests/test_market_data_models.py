import pytest
from pydantic import ValidationError

from tksessentials.data_models.market_data import (
    EXCHANGE,
    MACD,
    OHLCV,
    REQUEST,
    REQUEST_TYPE,
    RSI,
    TIMEFRAME,
    MarketDataAssignment,
)


def test_request_defaults_match_contract_expectations():
    request = REQUEST(recipe=OHLCV(), market="BTC-USDT")

    assert request.timeframe == TIMEFRAME.H_1
    assert request.exchange == EXCHANGE.BINANCE
    assert request.request_type == REQUEST_TYPE.HISTORICAL


def test_request_rejects_invalid_recipe_payload():
    with pytest.raises(ValidationError):
        REQUEST(
            recipe={"name": "rsi", "length": 0},
            market="BTC-USDT",
        )


def test_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        REQUEST(
            recipe={"name": "ohlcv"},
            market="BTC-USDT",
            unknown_field="value",
        )


def test_request_serialization_is_stable_for_rsi_recipe():
    request = REQUEST(
        recipe=RSI(length=7),
        market="ETH-USDT",
        timeframe=TIMEFRAME.H_6,
        exchange=EXCHANGE.BINANCE,
        request_type=REQUEST_TYPE.HISTORICAL,
    )

    assert request.model_dump(mode="json") == {
        "recipe": {"name": "rsi", "length": 7},
        "market": "ETH-USDT",
        "timeframe": "6h",
        "exchange": "BINANCE",
        "request_type": "historical",
    }


def test_recipe_parameter_order_for_macd_is_stable():
    macd = MACD(fast=10, slow=30, signal=8)

    assert list(macd.model_dump().keys()) == ["name", "fast", "slow", "signal"]


def test_assignment_envelope_supports_alias_and_default_flag():
    request = REQUEST(recipe=OHLCV(), market="BTC-USDT")
    assignment = MarketDataAssignment(request=request)

    dumped = assignment.model_dump(mode="json", by_alias=True)
    assert dumped["Market data requested"] is True
    assert dumped["request"]["recipe"]["name"] == "ohlcv"

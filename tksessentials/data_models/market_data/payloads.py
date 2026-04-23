"""Payload models for shared market-data contracts."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .value_objects import EXCHANGE, REQUEST_TYPE, TIMEFRAME


class MarketDataPayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RSI(MarketDataPayloadModel):
    name: Literal["rsi"] = "rsi"
    length: int = Field(default=14, ge=1)


class MACD(MarketDataPayloadModel):
    name: Literal["macd"] = "macd"
    fast: int = Field(default=12, ge=1)
    slow: int = Field(default=26, ge=1)
    signal: int = Field(default=9, ge=1)


class OHLCV(MarketDataPayloadModel):
    name: Literal["ohlcv"] = "ohlcv"


class REQUEST(MarketDataPayloadModel):
    recipe: Annotated[Union[RSI, MACD, OHLCV], Field(discriminator="name")]
    market: str
    timeframe: TIMEFRAME = TIMEFRAME.H_1
    exchange: EXCHANGE = EXCHANGE.BINANCE
    request_type: REQUEST_TYPE = REQUEST_TYPE.HISTORICAL


class MarketDataAssignment(MarketDataPayloadModel):
    market_data_requested: bool = Field(default=True, alias="Market data requested")
    request: REQUEST

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

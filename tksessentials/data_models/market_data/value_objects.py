"""Value objects for shared market-data contracts."""

from enum import Enum


class TIMEFRAME(str, Enum):
    H_1 = "1h"
    H_4 = "4h"
    H_6 = "6h"
    D_1 = "1d"


class EXCHANGE(str, Enum):
    BINANCE = "BINANCE"
    KUCOIN = "KUCOIN"
    COINBASE = "COINBASE"


class REQUEST_TYPE(str, Enum):
    HISTORICAL = "historical"
    REAL_TIME = "real_time"
    COMBINED = "combined"

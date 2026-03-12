import pytest
from pydantic import ValidationError

from tksessentials.data_models import (
    AggregateType,
    Direction,
    IntentStatus,
    LiquidityType,
    OrderCanceled,
    OrderFill,
    OrderFilled,
    OrderRequest,
    OrderSnapshot,
    OrderStatus,
    OrderType,
    SignalProvider,
    SignalStatus,
    Side,
    Trade,
    TradeCanceled,
    TradeClosed,
    TradeSnapshot,
    TradeStatus,
    TradingSignal,
    TradingSignalColdReason,
    TradingSignalCreated,
    TradingSignalFuture,
    TradingSignalIntent,
    TradingSignalIntentCanceled,
    TradingSignalIntentFuture,
    TradingSignalIntentGranted,
    TradingSignalIntentRejected,
    TradingSignalIntentRejectionReason,
    TradingSignalIntentSnapshot,
    TradingSignalIntentSpot,
    TradingSignalInvalidated,
    TradingSignalQualifiedCold,
    TradingSignalQualifiedHot,
    TradingSignalRejected,
    TradingSignalRejectionReason,
    TradingSignalSnapshot,
    TradingSignalSpot,
)


def _trading_signal_intent(created_at: int = 100) -> TradingSignalIntent:
    return TradingSignalIntent(
        intent_id="intent-1",
        signal_provider=SignalProvider(
            signal_provider_id="provider-a",
            signal_provider_name="Provider A",
        ),
        signal_provider_signal_id="provider-sig-1",
        signal_provider_trade_id="provider-trade-1",
        strategy_id="strategy-a",
        market="BTC/USDT",
        side=Side.BUY,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        target_price=100.0,
        take_profit=110.0,
        stop_loss=95.0,
        size_pct=25.0,
        is_hot=True,
        created_at=created_at,
        rationale="breakout setup",
    )


def _trading_signal(created_at: int = 100, prm_granted_at: int = 150) -> TradingSignal:
    return _trading_signal_intent(created_at=created_at).grant(
        signal_id="sig-1",
        prm_granted_at=prm_granted_at,
    )


def _order_request(order_type: OrderType = OrderType.LIMIT) -> OrderRequest:
    kwargs = {
        "order_id": "order-1",
        "intent_id": "intent-1",
        "trade_id": "trade-1",
        "market": "BTC/USDT",
        "side": Side.BUY,
        "order_type": order_type,
        "quantity": 1.5,
        "venue": "binance",
    }
    if order_type == OrderType.LIMIT:
        kwargs["limit_price"] = 100.0
    return OrderRequest(**kwargs)


def _trade(status: TradeStatus = TradeStatus.OPEN) -> Trade:
    return Trade(
        trade_id="trade-1",
        signal_id="sig-1",
        signal_provider_trade_id="provider-trade-1",
        market="BTC/USDT",
        direction=Direction.LONG,
        status=status,
        opened_at=150,
        entry_qty=2.0,
        exit_qty=0.5,
        avg_entry_price=100.0,
        realized_pnl=12.0,
    )


def test_trading_signal_intent_properties_are_semantically_useful():
    intent = _trading_signal_intent()

    assert intent.is_exit_signal is False
    assert intent.order_type == OrderType.LIMIT
    assert intent.signal_provider.signal_provider_id == "provider-a"


def test_trading_signal_intent_defaults_signal_provider_to_tks():
    intent = TradingSignalIntent(
        intent_id="intent-default",
        strategy_id="strategy-a",
        market="BTC/USDT",
        side=Side.BUY,
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        size_pct=10.0,
    )

    assert intent.signal_provider.signal_provider_id == "tks"
    assert intent.signal_provider.signal_provider_name == "TKS"


def test_trading_signal_intent_can_expire():
    intent = _trading_signal_intent().model_copy(update={"valid_until": 100})

    assert intent.can_expire(100) is True
    assert intent.can_expire(99) is False


def test_trading_signal_intent_rejects_blank_market():
    with pytest.raises(ValidationError):
        TradingSignalIntent(
            intent_id="intent-1",
            strategy_id="strategy-a",
            market="   ",
            side=Side.BUY,
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            size_pct=10.0,
        )


def test_trading_signal_intent_grant_materializes_publishable_signal():
    signal = _trading_signal()

    assert signal.signal_id == "sig-1"
    assert signal.intent_id == "intent-1"
    assert signal.created_at == 100
    assert signal.prm_granted_at == 150
    assert signal.signal_provider_signal_id == "provider-sig-1"


def test_trading_signal_rejects_prm_grant_before_intent_creation():
    with pytest.raises(ValidationError):
        _trading_signal_intent(created_at=100).grant(
            signal_id="sig-1",
            prm_granted_at=99,
        )


def test_spot_intent_and_signal_enforce_long_only():
    with pytest.raises(ValidationError):
        TradingSignalIntentSpot(
            intent_id="intent-spot",
            strategy_id="strategy-a",
            market="BTC/USDT",
            side=Side.BUY,
            direction=Direction.SHORT,
            order_type=OrderType.MARKET,
            size_pct=10.0,
        )

    signal = TradingSignalIntentSpot(
        intent_id="intent-spot",
        strategy_id="strategy-a",
        market="BTC/USDT",
        side=Side.BUY,
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        size_pct=10.0,
        created_at=100,
    ).grant(signal_id="sig-spot", prm_granted_at=200)

    assert isinstance(signal, TradingSignalSpot)
    assert signal.direction == Direction.LONG


def test_futures_signal_allows_short_direction():
    signal = TradingSignalIntentFuture(
        intent_id="intent-fut",
        strategy_id="strategy-a",
        market="BTC/USDT",
        side=Side.SELL,
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        size_pct=10.0,
        created_at=100,
    ).grant(signal_id="sig-fut", prm_granted_at=200)

    assert isinstance(signal, TradingSignalFuture)
    assert signal.direction == Direction.SHORT


def test_order_request_knows_if_it_is_limit():
    order = _order_request()

    assert order.is_limit_order is True


def test_limit_order_requires_limit_price():
    with pytest.raises(ValidationError):
        OrderRequest(
            order_id="order-1",
            intent_id="intent-1",
            market="BTC/USDT",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
        )


def test_trade_properties_report_open_state():
    trade = _trade()

    assert trade.net_qty == 1.5
    assert trade.is_closed is False


def test_domain_event_new_builds_trading_signal_event():
    signal = _trading_signal()

    event = TradingSignalCreated.new(
        aggregate_id=signal.signal_id,
        correlation_id=signal.signal_id,
        source="strategy-pod",
        payload=signal,
    )

    assert event.event_type == "trading_signal_created"
    assert event.aggregate_type == AggregateType.SIGNAL
    assert event.aggregate_id == signal.signal_id
    assert event.payload.prm_granted_at == 150


def test_invalidated_trading_signal_event_can_carry_raw_payload():
    event = TradingSignalInvalidated.new(
        aggregate_id="sig-raw-1",
        payload={"signal_provider_signal_id": "raw-1"},
        reason="missing market",
    )

    assert event.event_type == "trading_signal_invalidated"
    assert event.reason == "missing market"
    assert event.payload["signal_provider_signal_id"] == "raw-1"


def test_trading_signal_intent_granted_and_rejected_events_capture_traceability():
    intent = _trading_signal_intent()

    granted_event = TradingSignalIntentGranted.new(
        aggregate_id=intent.intent_id,
        payload=intent,
        signal_id="sig-1",
        prm_granted_at=150,
    )
    rejected_event = TradingSignalIntentRejected.new(
        aggregate_id=intent.intent_id,
        payload=intent,
        reasons=[TradingSignalIntentRejectionReason.PRM_REJECTED],
        reason_detail="Daily risk budget exhausted.",
    )

    assert granted_event.event_type == "trading_signal_intent_granted"
    assert granted_event.signal_id == "sig-1"
    assert granted_event.prm_granted_at == 150
    assert rejected_event.event_type == "trading_signal_intent_rejected"
    assert rejected_event.reasons == [TradingSignalIntentRejectionReason.PRM_REJECTED]
    assert rejected_event.reason_detail == "Daily risk budget exhausted."


def test_trading_signal_rejected_and_cold_events_use_structured_reason_enums():
    signal = _trading_signal()

    rejected_event = TradingSignalRejected.new(
        aggregate_id=signal.signal_id,
        payload=signal,
        reasons=[TradingSignalRejectionReason.INVALID_DATA],
    )
    cold_event = TradingSignalQualifiedCold.new(
        aggregate_id=signal.signal_id,
        payload=signal,
        reasons=[TradingSignalColdReason.SYSTEM_IS_COLD],
    )

    assert rejected_event.reasons == [TradingSignalRejectionReason.INVALID_DATA]
    assert cold_event.reasons == [TradingSignalColdReason.SYSTEM_IS_COLD]


def test_order_fill_and_fill_event_are_distinct_models():
    fill = OrderFill(
        fill_id="fill-1",
        order_id="order-1",
        trade_id="trade-1",
        market="BTC/USDT",
        side=Side.BUY,
        filled_qty=1.0,
        filled_price=101.0,
        fee=0.1,
        liquidity=LiquidityType.TAKER,
    )

    event = OrderFilled.new(
        aggregate_id=fill.order_id,
        causation_id="order-placed-1",
        payload=fill,
    )

    assert event.event_type == "order_filled"
    assert event.payload.filled_qty == 1.0
    assert event.aggregate_id == "order-1"


def test_snapshots_capture_granted_and_rejected_trading_signal_intents():
    signal_snapshot = TradingSignalSnapshot(
        trading_signal=_trading_signal(),
        status=SignalStatus.QUALIFIED_HOT,
    )
    granted_intent_snapshot = TradingSignalIntentSnapshot(
        trading_signal_intent=_trading_signal_intent(),
        status=IntentStatus.GRANTED,
        granted_at=150,
        granted_signal_id="sig-1",
    )
    rejected_intent_snapshot = TradingSignalIntentSnapshot(
        trading_signal_intent=_trading_signal_intent(),
        status=IntentStatus.REJECTED,
        rejection_reasons=[TradingSignalIntentRejectionReason.STRATEGY_PRM_REJECTED],
        reason_detail="Strategy PRM vetoed publication.",
    )
    order_snapshot = OrderSnapshot(order=_order_request(), status=OrderStatus.PLACED)
    trade_snapshot = TradeSnapshot(trade=_trade(TradeStatus.CLOSED), status=TradeStatus.CLOSED)

    assert signal_snapshot.is_terminal is True
    assert granted_intent_snapshot.is_active is False
    assert granted_intent_snapshot.granted_at == 150
    assert granted_intent_snapshot.granted_signal_id == "sig-1"
    assert rejected_intent_snapshot.rejection_reasons == [
        TradingSignalIntentRejectionReason.STRATEGY_PRM_REJECTED
    ]
    assert order_snapshot.is_terminal is False
    assert trade_snapshot.is_terminal is True


def test_cancel_and_close_events_can_add_reasons():
    order_event = OrderCanceled.new(
        aggregate_id="order-1",
        payload=_order_request(),
        reason="risk-off",
    )
    trade_event = TradeClosed.new(
        aggregate_id="trade-1",
        payload=_trade(TradeStatus.CLOSED),
    )
    trade_canceled_event = TradeCanceled.new(
        aggregate_id="trade-1",
        payload=_trade(TradeStatus.CANCELED),
        reason="risk-off",
    )
    intent_event = TradingSignalIntentCanceled.new(
        aggregate_id="intent-1",
        payload=_trading_signal_intent(),
        reason="stale setup",
    )
    signal_event = TradingSignalQualifiedHot.new(
        aggregate_id="sig-1",
        payload=_trading_signal(),
    )

    assert order_event.reason == "risk-off"
    assert trade_event.event_type == "trade_closed"
    assert trade_canceled_event.reason == "risk-off"
    assert intent_event.reason == "stale setup"
    assert signal_event.event_type == "trading_signal_qualified_hot"

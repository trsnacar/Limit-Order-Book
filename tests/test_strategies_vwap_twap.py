"""Tests for TWAP and VWAP strategies."""

import pytest

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderType, Side, TimeInForce
from lob_py.order import Order
from lob_py.strategies import TWAPStrategy, VWAPStrategy


def test_twap_basic():
    """Test TWAP strategy generates orders over time slices."""
    book = LimitOrderBook("BTCUSDT")
    strategy = TWAPStrategy(
        side=Side.BUY,
        total_quantity=100.0,
        start_ts=0.0,
        end_ts=100.0,
        symbol="BTCUSDT",
        num_slices=4,
    )

    # Simulate market data at different times
    mid_price = 100.0

    # First slice (t=0)
    orders1 = strategy.on_market_data(0.0, mid_price, book)
    assert len(orders1) == 1
    assert orders1[0].quantity == 25.0  # 100 / 4

    # Second slice (t=25)
    orders2 = strategy.on_market_data(25.0, mid_price, book)
    assert len(orders2) == 1
    # Remaining should be 75, divided by 3 remaining slices = 25
    assert orders2[0].quantity == 25.0

    # Third slice (t=50)
    orders3 = strategy.on_market_data(50.0, mid_price, book)
    assert len(orders3) == 1
    assert orders3[0].quantity == 25.0

    # Fourth slice (t=75)
    orders4 = strategy.on_market_data(75.0, mid_price, book)
    assert len(orders4) == 1
    assert orders4[0].quantity == 25.0

    # Total quantity should be ~100
    total_qty = sum(o.quantity for o in orders1 + orders2 + orders3 + orders4)
    assert abs(total_qty - 100.0) < 0.01


def test_twap_progress():
    """Test TWAP strategy tracks execution progress."""
    book = LimitOrderBook("BTCUSDT")
    strategy = TWAPStrategy(
        side=Side.BUY,
        total_quantity=100.0,
        start_ts=0.0,
        end_ts=100.0,
        symbol="BTCUSDT",
        num_slices=10,
    )

    # Simulate fills
    from lob_py.events import Event, EventType

    # Create mock fill events
    fill_event = Event(
        type=EventType.TRADE,
        order_id="test-order",
        price=100.0,
        quantity=10.0,
    )

    # Add order to strategy's open_orders for on_fill to work
    from lob_py.order import Order

    test_order = Order(
        order_id="test-order",
        client_id="strategy-TWAP",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=10.0,
        remaining_quantity=10.0,
        time_in_force=TimeInForce.IOC,
        flags=set(),
        timestamp=0.0,
    )
    strategy.open_orders["test-order"] = test_order

    strategy.on_fill([fill_event])

    assert strategy.executed_quantity == 10.0
    assert strategy.avg_fill_price == 100.0
    assert strategy.get_progress() == 0.1  # 10/100


def test_vwap_basic():
    """Test VWAP strategy (simplified MVP version)."""
    book = LimitOrderBook("BTCUSDT")
    strategy = VWAPStrategy(
        side=Side.BUY,
        total_quantity=100.0,
        start_ts=0.0,
        end_ts=100.0,
        symbol="BTCUSDT",
        num_slices=4,
    )

    mid_price = 100.0

    # Generate orders (similar to TWAP in MVP)
    orders1 = strategy.on_market_data(0.0, mid_price, book)
    assert len(orders1) == 1

    orders2 = strategy.on_market_data(25.0, mid_price, book)
    assert len(orders2) == 1

    # Strategy should generate orders
    assert strategy.name == "VWAP"


def test_strategy_is_done():
    """Test strategy completion check."""
    book = LimitOrderBook("BTCUSDT")
    strategy = TWAPStrategy(
        side=Side.BUY,
        total_quantity=100.0,
        start_ts=0.0,
        end_ts=100.0,
        symbol="BTCUSDT",
    )

    assert not strategy.is_done()

    # Simulate full execution
    from lob_py.events import Event, EventType
    from lob_py.order import Order

    test_order = Order(
        order_id="test-order",
        client_id="strategy-TWAP",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=100.0,
        remaining_quantity=100.0,
        time_in_force=TimeInForce.IOC,
        flags=set(),
        timestamp=0.0,
    )
    strategy.open_orders["test-order"] = test_order

    fill_event = Event(
        type=EventType.TRADE,
        order_id="test-order",
        price=100.0,
        quantity=100.0,
    )
    strategy.on_fill([fill_event])

    assert strategy.is_done()


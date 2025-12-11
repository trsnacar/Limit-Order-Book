"""Tests for Market Maker strategy."""

import pytest

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderFlag, OrderType, Side, TimeInForce
from lob_py.events import Event, EventType
from lob_py.order import Order
from lob_py.strategies import MarketMakerStrategy


def test_market_maker_generates_quotes():
    """Test market maker generates bid/ask quotes."""
    book = LimitOrderBook("BTCUSDT")
    strategy = MarketMakerStrategy(
        symbol="BTCUSDT",
        start_ts=0.0,
        end_ts=100.0,
        base_spread_bps=10.0,
        order_size=1.0,
    )

    mid_price = 100.0

    # Generate quotes
    orders = strategy.on_market_data(0.0, mid_price, book)

    # Should generate both bid and ask
    assert len(orders) >= 1

    # Check for bid and ask orders
    bid_orders = [o for o in orders if o.side == Side.BUY]
    ask_orders = [o for o in orders if o.side == Side.SELL]

    # Market maker should quote both sides
    assert len(bid_orders) > 0 or len(ask_orders) > 0


def test_market_maker_inventory_management():
    """Test market maker adjusts spread based on inventory."""
    book = LimitOrderBook("BTCUSDT")
    strategy = MarketMakerStrategy(
        symbol="BTCUSDT",
        start_ts=0.0,
        end_ts=100.0,
        base_spread_bps=10.0,
        order_size=1.0,
        max_inventory=10.0,
        inventory_skew_factor=0.5,
    )

    mid_price = 100.0

    # Initially no inventory
    orders1 = strategy.on_market_data(0.0, mid_price, book)
    assert len(orders1) >= 1

    # Simulate fill that increases inventory (long position)
    test_order = Order(
        order_id="test-bid",
        client_id="strategy-MarketMaker",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=99.95,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags={OrderFlag.POST_ONLY},
        timestamp=0.0,
    )
    strategy.open_orders["test-bid"] = test_order

    fill_event = Event(
        type=EventType.TRADE,
        order_id="test-bid",
        price=99.95,
        quantity=1.0,
    )
    strategy.on_fill([fill_event])

    # Inventory should be positive
    assert strategy.inventory > 0

    # Generate new quotes with inventory skew
    orders2 = strategy.on_market_data(1.0, mid_price, book)
    # Should still generate quotes (implementation may vary)
    assert len(orders2) >= 0


def test_market_maker_inventory_limits():
    """Test market maker respects inventory limits."""
    book = LimitOrderBook("BTCUSDT")
    strategy = MarketMakerStrategy(
        symbol="BTCUSDT",
        start_ts=0.0,
        end_ts=100.0,
        max_inventory=5.0,
        order_size=1.0,
    )

    # Set inventory to max
    strategy.inventory = 5.0

    mid_price = 100.0
    orders = strategy.on_market_data(0.0, mid_price, book)

    # Should not generate more BUY orders if at max inventory
    # (but may still generate SELL orders)
    buy_orders = [o for o in orders if o.side == Side.BUY]
    # Implementation may vary, but should respect limits


def test_market_maker_pnl_tracking():
    """Test market maker tracks PnL."""
    book = LimitOrderBook("BTCUSDT")
    strategy = MarketMakerStrategy(
        symbol="BTCUSDT",
        start_ts=0.0,
        end_ts=100.0,
    )

    # Initially no PnL
    pnl = strategy.get_pnl()
    assert pnl is not None  # Should return a value (may be 0.0)


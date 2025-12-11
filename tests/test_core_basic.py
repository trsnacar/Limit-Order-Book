"""Basic tests for core limit order book functionality."""

import pytest

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderType, Side, TimeInForce
from lob_py.events import EventType
from lob_py.order import Order


def test_basic_match():
    """Test basic order matching: 1 BUY + 1 SELL at matching prices."""
    book = LimitOrderBook("BTCUSDT")

    # Add BUY order
    buy_order = Order(
        order_id="1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    events1 = book.add_order(buy_order)

    # Should be added to book (no match yet)
    assert len(events1) == 1
    assert events1[0].type == EventType.NEW

    # Add SELL order that matches
    sell_order = Order(
        order_id="2",
        client_id="bob",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=99.5,
        quantity=0.5,
        remaining_quantity=0.5,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=1.0,
    )
    events2 = book.add_order(sell_order)

    # Should have TRADE and DONE events
    assert len(events2) >= 1
    trade_events = [e for e in events2 if e.type == EventType.TRADE]
    assert len(trade_events) == 1
    assert trade_events[0].price == 99.5  # Maker price
    assert trade_events[0].quantity == 0.5

    # Check remaining quantity
    buy_order_after = book.get_order("1")
    assert buy_order_after is not None
    assert buy_order_after.remaining_quantity == 0.5


def test_price_priority():
    """Test that better prices match first."""
    book = LimitOrderBook("BTCUSDT")

    # Add multiple SELL orders at different prices
    sell1 = Order(
        order_id="sell1",
        client_id="bob",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=101.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    sell2 = Order(
        order_id="sell2",
        client_id="charlie",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,  # Better price
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=1.0,
    )

    book.add_order(sell1)
    book.add_order(sell2)

    # Add BUY order that should match with better price first
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=102.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=2.0,
    )
    events = book.add_order(buy_order)

    # Should match with sell2 (better price) first
    trade_events = [e for e in events if e.type == EventType.TRADE]
    assert len(trade_events) == 1
    assert trade_events[0].matched_order_id == "sell2"
    assert trade_events[0].price == 100.0


def test_time_priority():
    """Test that earlier orders at same price match first (FIFO)."""
    book = LimitOrderBook("BTCUSDT")

    # Add two SELL orders at same price
    sell1 = Order(
        order_id="sell1",
        client_id="bob",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=0.5,
        remaining_quantity=0.5,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    sell2 = Order(
        order_id="sell2",
        client_id="charlie",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,  # Same price
        quantity=0.5,
        remaining_quantity=0.5,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=1.0,  # Later timestamp
    )

    book.add_order(sell1)
    book.add_order(sell2)

    # Add BUY order that should match with first order
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=2.0,
    )
    events = book.add_order(buy_order)

    # Should match with sell1 first (FIFO)
    trade_events = [e for e in events if e.type == EventType.TRADE]
    assert len(trade_events) == 2
    assert trade_events[0].matched_order_id == "sell1"
    assert trade_events[1].matched_order_id == "sell2"


def test_cancel_order():
    """Test order cancellation."""
    book = LimitOrderBook("BTCUSDT")

    # Add order
    order = Order(
        order_id="1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    book.add_order(order)

    # Cancel order
    events = book.cancel_order("1")
    assert len(events) == 1
    assert events[0].type == EventType.CANCEL

    # Order should be removed
    assert book.get_order("1") is None


def test_get_best_prices():
    """Test getting best bid/ask prices."""
    book = LimitOrderBook("BTCUSDT")

    # Initially no prices
    assert book.get_best_bid() is None
    assert book.get_best_ask() is None
    assert book.get_mid_price() is None

    # Add BUY order
    buy_order = Order(
        order_id="1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    book.add_order(buy_order)

    best_bid = book.get_best_bid()
    assert best_bid is not None
    assert best_bid[0] == 100.0
    assert best_bid[1] == 1.0

    # Add SELL order
    sell_order = Order(
        order_id="2",
        client_id="bob",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=101.0,
        quantity=0.5,
        remaining_quantity=0.5,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=1.0,
    )
    book.add_order(sell_order)

    best_ask = book.get_best_ask()
    assert best_ask is not None
    assert best_ask[0] == 101.0
    assert best_ask[1] == 0.5

    mid = book.get_mid_price()
    assert mid == 100.5


def test_get_depth():
    """Test getting order book depth."""
    book = LimitOrderBook("BTCUSDT")

    # Add multiple orders
    for i in range(3):
        order = Order(
            order_id=f"buy{i}",
            client_id="alice",
            side=Side.BUY,
            type=OrderType.LIMIT,
            price=100.0 - i,
            quantity=1.0,
            remaining_quantity=1.0,
            time_in_force=TimeInForce.GTC,
            flags=set(),
            timestamp=float(i),
        )
        book.add_order(order)

    depth = book.get_depth(levels=5)
    assert len(depth["bids"]) == 3
    assert depth["bids"][0][0] == 100.0  # Highest price first


"""Tests for time-in-force policies."""

import pytest

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderType, Side, TimeInForce
from lob_py.events import EventType
from lob_py.order import Order


def test_ioc_partial_fill():
    """Test IOC: partial fill + auto-cancel remaining."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL order
    sell_order = Order(
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
    book.add_order(sell_order)

    # Add IOC BUY order for more than available
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,  # More than available
        remaining_quantity=1.0,
        time_in_force=TimeInForce.IOC,
        flags=set(),
        timestamp=1.0,
    )
    events = book.add_order(buy_order)

    # Should have TRADE for partial fill and CANCEL for remaining
    trade_events = [e for e in events if e.type == EventType.TRADE]
    cancel_events = [e for e in events if e.type == EventType.CANCEL]

    assert len(trade_events) == 1
    assert trade_events[0].quantity == 0.5
    assert len(cancel_events) == 1
    assert cancel_events[0].order_id == "buy1"
    assert "IOC" in cancel_events[0].reason or cancel_events[0].reason == "IOC_REMAINING"


def test_ioc_no_match():
    """Test IOC: no match, immediate cancel."""
    book = LimitOrderBook("BTCUSDT")

    # Add IOC BUY order with no matching SELL
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.IOC,
        flags=set(),
        timestamp=0.0,
    )
    events = book.add_order(buy_order)

    # Should have CANCEL event
    cancel_events = [e for e in events if e.type == EventType.CANCEL]
    assert len(cancel_events) == 1
    assert cancel_events[0].order_id == "buy1"


def test_fok_complete_fill():
    """Test FOK: complete fill succeeds."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL orders
    for i in range(2):
        sell_order = Order(
            order_id=f"sell{i}",
            client_id="bob",
            side=Side.SELL,
            type=OrderType.LIMIT,
            price=100.0,
            quantity=0.5,
            remaining_quantity=0.5,
            time_in_force=TimeInForce.GTC,
            flags=set(),
            timestamp=float(i),
        )
        book.add_order(sell_order)

    # Add FOK BUY order for exact available quantity
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.FOK,
        flags=set(),
        timestamp=2.0,
    )
    events = book.add_order(buy_order)

    # Should have TRADE events, no REJECT
    trade_events = [e for e in events if e.type == EventType.TRADE]
    reject_events = [e for e in events if e.type == EventType.REJECT]

    assert len(trade_events) == 2
    assert len(reject_events) == 0


def test_fok_insufficient_liquidity():
    """Test FOK: insufficient liquidity, reject."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL order with less quantity
    sell_order = Order(
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
    book.add_order(sell_order)

    # Add FOK BUY order for more than available
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,  # More than available
        remaining_quantity=1.0,
        time_in_force=TimeInForce.FOK,
        flags=set(),
        timestamp=1.0,
    )
    events = book.add_order(buy_order)

    # Should have REJECT event, no TRADE
    reject_events = [e for e in events if e.type == EventType.REJECT]
    trade_events = [e for e in events if e.type == EventType.TRADE]

    assert len(reject_events) == 1
    assert reject_events[0].order_id == "buy1"
    assert "FOK" in reject_events[0].reason
    assert len(trade_events) == 0


def test_market_order_behavior():
    """Test market order fills as much as possible."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL orders
    for i in range(2):
        sell_order = Order(
            order_id=f"sell{i}",
            client_id="bob",
            side=Side.SELL,
            type=OrderType.LIMIT,
            price=100.0 + i,
            quantity=0.5,
            remaining_quantity=0.5,
            time_in_force=TimeInForce.GTC,
            flags=set(),
            timestamp=float(i),
        )
        book.add_order(sell_order)

    # Add MARKET BUY order
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.MARKET,
        price=None,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=2.0,
    )
    events = book.add_order(buy_order)

    # Should have TRADE events
    trade_events = [e for e in events if e.type == EventType.TRADE]
    assert len(trade_events) >= 1

    # Total filled should be limited by available liquidity
    total_filled = sum(e.quantity for e in trade_events if e.quantity)
    assert total_filled <= 1.0


"""Tests for order flags (POST_ONLY, STP)."""

import pytest

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderFlag, OrderType, Side, TimeInForce
from lob_py.events import EventType
from lob_py.order import Order


def test_post_only_reject():
    """Test POST_ONLY: reject if would match immediately."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL order
    sell_order = Order(
        order_id="sell1",
        client_id="bob",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    book.add_order(sell_order)

    # Add POST_ONLY BUY order that would match
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,  # Would match
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags={OrderFlag.POST_ONLY},
        timestamp=1.0,
    )
    events = book.add_order(buy_order)

    # Should have REJECT event
    reject_events = [e for e in events if e.type == EventType.REJECT]
    assert len(reject_events) == 1
    assert reject_events[0].order_id == "buy1"
    assert "POST_ONLY" in reject_events[0].reason


def test_post_only_accept():
    """Test POST_ONLY: accept if would not match immediately."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL order
    sell_order = Order(
        order_id="sell1",
        client_id="bob",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    book.add_order(sell_order)

    # Add POST_ONLY BUY order that would NOT match (price too low)
    buy_order = Order(
        order_id="buy1",
        client_id="alice",
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=99.0,  # Would not match
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags={OrderFlag.POST_ONLY},
        timestamp=1.0,
    )
    events = book.add_order(buy_order)

    # Should have NEW event (added to book)
    new_events = [e for e in events if e.type == EventType.NEW]
    assert len(new_events) == 1
    assert new_events[0].order_id == "buy1"


def test_stp_prevention():
    """Test STP: prevent self-trade with same client_id."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL order from alice
    sell_order = Order(
        order_id="sell1",
        client_id="alice",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    book.add_order(sell_order)

    # Add STP BUY order from same client_id
    buy_order = Order(
        order_id="buy1",
        client_id="alice",  # Same client_id
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags={OrderFlag.STP},
        timestamp=1.0,
    )
    events = book.add_order(buy_order)

    # Should NOT have TRADE event (STP prevented)
    trade_events = [e for e in events if e.type == EventType.TRADE]
    assert len(trade_events) == 0

    # Order should be added to book instead (or rejected, depending on implementation)
    # In our implementation, it should be added to book if no match occurred
    new_events = [e for e in events if e.type == EventType.NEW]
    assert len(new_events) == 1


def test_stp_no_flag():
    """Test that without STP flag, self-trade is allowed."""
    book = LimitOrderBook("BTCUSDT")

    # Add SELL order from alice
    sell_order = Order(
        order_id="sell1",
        client_id="alice",
        side=Side.SELL,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),
        timestamp=0.0,
    )
    book.add_order(sell_order)

    # Add BUY order from same client_id WITHOUT STP flag
    buy_order = Order(
        order_id="buy1",
        client_id="alice",  # Same client_id
        side=Side.BUY,
        type=OrderType.LIMIT,
        price=100.0,
        quantity=1.0,
        remaining_quantity=1.0,
        time_in_force=TimeInForce.GTC,
        flags=set(),  # No STP flag
        timestamp=1.0,
    )
    events = book.add_order(buy_order)

    # Should have TRADE event (self-trade allowed)
    trade_events = [e for e in events if e.type == EventType.TRADE]
    assert len(trade_events) == 1


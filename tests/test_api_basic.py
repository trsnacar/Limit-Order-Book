"""Basic tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from lob_py.api import get_app
from lob_py.enums import OrderFlag, OrderType, Side, TimeInForce


@pytest.fixture
def client():
    """Create test client."""
    app = get_app()
    return TestClient(app)


def test_create_order(client):
    """Test creating an order via API."""
    response = client.post(
        "/orders",
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": 100.0,
            "quantity": 1.0,
            "time_in_force": "GTC",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "order_id" in data
    assert "events" in data
    assert len(data["events"]) > 0


def test_create_matching_orders(client):
    """Test creating matching orders that trade."""
    # Create BUY order
    buy_response = client.post(
        "/orders",
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": 100.0,
            "quantity": 1.0,
            "time_in_force": "GTC",
        },
    )
    assert buy_response.status_code == 200

    # Create SELL order that matches
    sell_response = client.post(
        "/orders",
        json={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "LIMIT",
            "price": 99.5,
            "quantity": 0.5,
            "time_in_force": "GTC",
        },
    )
    assert sell_response.status_code == 200

    sell_data = sell_response.json()
    # Should have TRADE event
    trade_events = [e for e in sell_data["events"] if e["type"] == "TRADE"]
    assert len(trade_events) > 0


def test_get_best_prices(client):
    """Test getting best bid/ask prices."""
    # Add orders first
    client.post(
        "/orders",
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": 100.0,
            "quantity": 1.0,
        },
    )
    client.post(
        "/orders",
        json={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "LIMIT",
            "price": 101.0,
            "quantity": 0.5,
        },
    )

    # Get best prices
    response = client.get("/orderbook/best?symbol=BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert "best_bid" in data
    assert "best_ask" in data
    assert "mid_price" in data
    assert data["best_bid"] == [100.0, 1.0]
    assert data["best_ask"] == [101.0, 0.5]


def test_get_depth(client):
    """Test getting order book depth."""
    # Add multiple orders
    for i in range(3):
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "price": 100.0 - i,
                "quantity": 1.0,
            },
        )

    response = client.get("/orderbook/depth?symbol=BTCUSDT&levels=5")
    assert response.status_code == 200
    data = response.json()
    assert "bids" in data
    assert "asks" in data
    assert len(data["bids"]) == 3


def test_cancel_order(client):
    """Test canceling an order."""
    # Create order
    create_response = client.post(
        "/orders",
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": 100.0,
            "quantity": 1.0,
        },
    )
    order_id = create_response.json()["order_id"]

    # Cancel order
    cancel_response = client.post(
        f"/orders/{order_id}/cancel",
        json={"symbol": "BTCUSDT"},
    )
    assert cancel_response.status_code == 200
    data = cancel_response.json()
    assert data["order_id"] == order_id
    cancel_events = [e for e in data["events"] if e["type"] == "CANCEL"]
    assert len(cancel_events) > 0


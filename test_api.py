"""Test the API with sample requests."""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint."""
    print("1. Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    print()

def test_create_order():
    """Test creating an order."""
    print("2. Testing order creation...")
    order_data = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "price": 100.0,
        "quantity": 1.0,
        "time_in_force": "GTC"
    }
    response = requests.post(f"{BASE_URL}/orders", json=order_data)
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Order ID: {result['order_id']}")
    print(f"   Events: {len(result['events'])}")
    for event in result['events']:
        print(f"     - {event['type']}")
    print()
    return result['order_id']

def test_create_matching_order():
    """Test creating a matching order."""
    print("3. Testing matching order (should trade)...")
    order_data = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "price": 99.5,
        "quantity": 0.5,
        "time_in_force": "GTC"
    }
    response = requests.post(f"{BASE_URL}/orders", json=order_data)
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Order ID: {result['order_id']}")
    trade_events = [e for e in result['events'] if e['type'] == 'TRADE']
    print(f"   Trade events: {len(trade_events)}")
    if trade_events:
        print(f"   Trade price: {trade_events[0]['price']}")
        print(f"   Trade quantity: {trade_events[0]['quantity']}")
    print()

def test_get_best_prices():
    """Test getting best prices."""
    print("4. Testing best prices...")
    response = requests.get(f"{BASE_URL}/orderbook/best?symbol=BTCUSDT")
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Best bid: {result['best_bid']}")
    print(f"   Best ask: {result['best_ask']}")
    print(f"   Mid price: {result['mid_price']}")
    print()

def test_get_depth():
    """Test getting order book depth."""
    print("5. Testing order book depth...")
    response = requests.get(f"{BASE_URL}/orderbook/depth?symbol=BTCUSDT&levels=5")
    print(f"   Status: {response.status_code}")
    print(f"   Response text: {response.text[:200]}")
    if response.status_code == 200:
        result = response.json()
        print(f"   Bids levels: {len(result['bids'])}")
        print(f"   Asks levels: {len(result['asks'])}")
    print()

def test_metrics():
    """Test metrics endpoint."""
    print("6. Testing metrics endpoint...")
    response = requests.get(f"{BASE_URL}/metrics")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"   Counters: {len(result.get('counters', {}))}")
        print(f"   Gauges: {len(result.get('gauges', {}))}")
    print()

if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Testing Limit Order Book API")
    print("=" * 50)
    print()
    
    try:
        # Wait a bit for server to be ready
        print("Waiting for server to be ready...")
        time.sleep(2)
        
        test_health()
        test_create_order()
        test_create_matching_order()
        test_get_best_prices()
        test_get_depth()
        test_metrics()
        
        print("=" * 50)
        print("✅ All tests completed successfully!")
        print("=" * 50)
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to server.")
        print("   Make sure the server is running:")
        print("   python start_server.py")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


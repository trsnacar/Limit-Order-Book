"""Direct test of depth endpoint."""

from fastapi.testclient import TestClient
from lob_py.api import get_app

app = get_app()
client = TestClient(app)

# Create some orders first
print("Creating orders...")
client.post("/orders", json={
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "price": 100.0,
    "quantity": 1.0,
})

# Test depth
print("Testing depth endpoint...")
response = client.get("/orderbook/depth?symbol=BTCUSDT&levels=5")
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
if response.status_code == 200:
    print(f"JSON: {response.json()}")


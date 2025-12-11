"""Test script to check if server can start."""

import sys
import time

try:
    print("Importing modules...")
    from lob_py.api import get_app
    print("✓ Import successful")
    
    print("Creating app...")
    app = get_app()
    print("✓ App created")
    
    print("Testing health endpoint...")
    # Test with test client
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/health")
    print(f"✓ Health check: {response.status_code}")
    print(f"  Response: {response.json()}")
    
    print("\n✅ All tests passed! Server is ready.")
    print("\nTo start the server, run:")
    print("  uvicorn lob_py.api:get_app --host 0.0.0.0 --port 8000 --reload")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


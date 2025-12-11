"""Simple script to start the server."""

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting Limit Order Book API Server...")
    print("📍 Server will be available at: http://localhost:8000")
    print("📖 API docs: http://localhost:8000/docs")
    print("❤️  Health check: http://localhost:8000/health")
    print("\nPress Ctrl+C to stop the server\n")
    
    uvicorn.run(
        "lob_py.api:get_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


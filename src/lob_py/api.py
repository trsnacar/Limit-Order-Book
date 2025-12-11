"""FastAPI service for the limit order book."""

import asyncio
import json
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from lob_py.config import settings
from lob_py.core import LimitOrderBook
from lob_py.enums import EventType, OrderFlag, OrderType, Side, TimeInForce
from lob_py.events import Event
from lob_py.logging_config import logger
from lob_py.metrics import metrics
from lob_py.order import Order


# In-memory order book manager (thread-safe)
class OrderBookManager:
    """Manages multiple order books by symbol."""

    def __init__(self):
        self._books: dict[str, LimitOrderBook] = {}
        self._lock = asyncio.Lock()

    async def get_book(self, symbol: str) -> LimitOrderBook:
        """Get or create an order book for a symbol (thread-safe)."""
        async with self._lock:
            if symbol not in self._books:
                self._books[symbol] = LimitOrderBook(symbol, enable_cache=settings.enable_size_cache)
                if metrics:
                    metrics.gauge("orderbook.count", len(self._books))
            return self._books[symbol]

    def get_all_symbols(self) -> list[str]:
        """Get all symbols with active order books."""
        return list(self._books.keys())


# Global manager instance
manager = OrderBookManager()

# Global event queue for WebSocket
event_queue: asyncio.Queue[tuple[str, Event]] = asyncio.Queue()  # (symbol, event)


# Rate limiting
class RateLimiter:
    """Simple rate limiter for API endpoints."""
    
    def __init__(self, max_requests: int, window_seconds: float = 1.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check(self, key: str) -> bool:
        """Check if request is allowed. Returns True if allowed."""
        async with self._lock:
            now = time.time()
            # Clean old requests
            self.requests[key] = [t for t in self.requests[key] if now - t < self.window_seconds]
            
            if len(self.requests[key]) >= self.max_requests:
                return False
            
            self.requests[key].append(now)
            return True


# Global rate limiter
rate_limiter = RateLimiter(settings.rate_limit_per_second) if settings.rate_limit_enabled else None


# Pydantic models with validation
class OrderCreateRequest(BaseModel):
    """Request model for creating an order."""

    symbol: str = Field(..., min_length=1, max_length=20)
    side: Side
    type: OrderType
    price: float | None = Field(None, gt=0)
    quantity: float = Field(..., gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    flags: list[OrderFlag] | None = None
    client_id: str | None = Field(None, max_length=100)
    order_id: str | int | None = None

    @validator("price")
    def validate_price(cls, v, values):
        """Validate price is required for LIMIT orders."""
        if values.get("type") == OrderType.LIMIT and v is None:
            raise ValueError("price is required for LIMIT orders")
        return v


class EventModel(BaseModel):
    """Pydantic model for Event."""

    type: EventType
    order_id: str | int | None = None
    matched_order_id: str | int | None = None
    price: float | None = None
    quantity: float | None = None
    reason: str | None = None
    timestamp: float | int | None = None
    data: dict[str, Any] | None = None

    @classmethod
    def from_event(cls, event: Event) -> "EventModel":
        """Create EventModel from Event."""
        return cls(
            type=event.type,
            order_id=event.order_id,
            matched_order_id=event.matched_order_id,
            price=event.price,
            quantity=event.quantity,
            reason=event.reason,
            timestamp=event.timestamp,
            data=event.data,
        )


class OrderResponse(BaseModel):
    """Response model for order operations."""

    order_id: str | int
    events: list[EventModel]


class BestPriceResponse(BaseModel):
    """Response model for best price query."""

    symbol: str
    best_bid: tuple[float, float] | None = None
    best_ask: tuple[float, float] | None = None
    mid_price: float | None = None


class DepthResponse(BaseModel):
    """Response model for order book depth."""

    symbol: str
    bids: list[list[float]]  # [price, size]
    asks: list[list[float]]  # [price, size]
    
    @classmethod
    def from_depth(cls, symbol: str, depth: dict[str, list[tuple[float, float]]]) -> "DepthResponse":
        """Create DepthResponse from depth dict."""
        return cls(
            symbol=symbol,
            bids=[[price, size] for price, size in depth["bids"]],
            asks=[[price, size] for price, size in depth["asks"]],
        )


class CancelRequest(BaseModel):
    """Request model for canceling an order."""

    symbol: str


class AmendRequest(BaseModel):
    """Request model for amending an order."""

    symbol: str
    new_price: float | None = None
    new_quantity: float | None = None


# Helper function to push events to queue
async def push_events(symbol: str, events: list[Event]) -> None:
    """Push events to the global event queue."""
    for event in events:
        await event_queue.put((symbol, event))
        if metrics:
            metrics.increment("events.produced", tags={"type": event.type.value, "symbol": symbol})


# FastAPI app
def get_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(
        title="Limit Order Book API",
        description="REST and WebSocket API for limit order book operations",
        version="0.2.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request timing middleware
    @app.middleware("http")
    async def timing_middleware(request: Request, call_next):
        """Track request timing."""
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        if metrics:
            metrics.timer("http.request.duration", duration, tags={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            })
        
        response.headers["X-Process-Time"] = str(duration)
        return response

    # Rate limiting middleware
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting."""
        if rate_limiter and request.url.path.startswith("/orders"):
            client_ip = request.client.host if request.client else "unknown"
            if not await rate_limiter.check(client_ip):
                if metrics:
                    metrics.increment("rate_limit.exceeded")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "Rate limit exceeded"}
                )
        return await call_next(request)

    # Counter for auto-generating order IDs
    order_id_counter = defaultdict(int)

    def generate_order_id(symbol: str) -> str:
        """Generate a unique order ID for a symbol."""
        order_id_counter[symbol] += 1
        return f"{symbol}-{order_id_counter[symbol]}"

    @app.post("/orders", response_model=OrderResponse)
    async def create_order(request: OrderCreateRequest) -> OrderResponse:
        """Create a new order."""
        timer = metrics.time_it("order.create") if metrics else None
        if timer:
            timer.__enter__()
        
        try:
            book = await manager.get_book(request.symbol)

            # Generate order ID if not provided
            order_id = request.order_id or generate_order_id(request.symbol)

            # Convert flags list to set
            flags_set = set(request.flags) if request.flags else set()

            # Create order
            order = Order(
                order_id=order_id,
                client_id=request.client_id,
                side=request.side,
                type=request.type,
                price=request.price,
                quantity=request.quantity,
                remaining_quantity=request.quantity,
                time_in_force=request.time_in_force,
                flags=flags_set,
                timestamp=time.time(),
                user_data={},
            )

            # Add order to book
            events = book.add_order(order)

            # Track metrics
            if metrics:
                metrics.increment("orders.created", tags={"symbol": request.symbol, "side": request.side.value})
                trade_count = sum(1 for e in events if e.type == EventType.TRADE)
                if trade_count > 0:
                    metrics.increment("orders.matched", tags={"symbol": request.symbol})

            # Push events to WebSocket queue
            await push_events(request.symbol, events)

            logger.info("Order created", extra={
                "order_id": order_id,
                "symbol": request.symbol,
                "side": request.side.value,
                "events_count": len(events),
            })

            return OrderResponse(
                order_id=order_id,
                events=[EventModel.from_event(e) for e in events],
            )
        except Exception as e:
            logger.error("Error creating order", exc_info=True, extra={"error": str(e)})
            if metrics:
                metrics.increment("orders.error", tags={"symbol": request.symbol})
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if timer:
                timer.__exit__(None, None, None)

    @app.post("/orders/{order_id}/cancel", response_model=OrderResponse)
    async def cancel_order(order_id: str | int, request: CancelRequest) -> OrderResponse:
        """Cancel an order."""
        try:
            book = await manager.get_book(request.symbol)
            events = book.cancel_order(order_id)

            if metrics:
                metrics.increment("orders.cancelled", tags={"symbol": request.symbol})

            await push_events(request.symbol, events)

            return OrderResponse(
                order_id=order_id,
                events=[EventModel.from_event(e) for e in events],
            )
        except Exception as e:
            logger.error("Error cancelling order", exc_info=True, extra={"order_id": order_id, "error": str(e)})
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/orders/{order_id}/amend", response_model=OrderResponse)
    async def amend_order(order_id: str | int, request: AmendRequest) -> OrderResponse:
        """Amend an order."""
        book = manager.get_book(request.symbol)
        events = book.amend_order(order_id, request.new_price, request.new_quantity)

        # Push events to WebSocket queue
        push_events(request.symbol, events)

        return OrderResponse(
            order_id=order_id,
            events=[EventModel.from_event(e) for e in events],
        )

    @app.get("/orderbook/best", response_model=BestPriceResponse)
    async def get_best_prices(symbol: str) -> BestPriceResponse:
        """Get best bid, ask, and mid price."""
        try:
            book = await manager.get_book(symbol)
            return BestPriceResponse(
                symbol=symbol,
                best_bid=book.get_best_bid(),
                best_ask=book.get_best_ask(),
                mid_price=book.get_mid_price(),
            )
        except Exception as e:
            logger.error("Error getting best prices", exc_info=True, extra={"symbol": symbol, "error": str(e)})
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/orderbook/depth", response_model=DepthResponse)
    async def get_depth(symbol: str, levels: int = 10) -> DepthResponse:
        """Get order book depth."""
        try:
            book = await manager.get_book(symbol)
            depth = book.get_depth(levels)
            return DepthResponse.from_depth(symbol, depth)
        except Exception as e:
            logger.error("Error getting depth", exc_info=True, extra={"symbol": symbol, "error": str(e)})
            raise HTTPException(status_code=500, detail=str(e))

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """WebSocket endpoint for streaming events."""
        await websocket.accept()
        try:
            while True:
                # Wait for event from queue
                symbol, event = await event_queue.get()
                await websocket.send_json(
                    {
                        "symbol": symbol,
                        "event": EventModel.from_event(event).model_dump(),
                    }
                )
        except WebSocketDisconnect:
            pass

    @app.websocket("/ws/quotes")
    async def websocket_quotes(websocket: WebSocket, symbol: str, interval_ms: int = 100):
        """WebSocket endpoint for streaming quotes (best bid/ask/mid)."""
        await websocket.accept()
        try:
            while True:
                book = manager.get_book(symbol)
                best_bid = book.get_best_bid()
                best_ask = book.get_best_ask()
                mid_price = book.get_mid_price()

                await websocket.send_json(
                    {
                        "symbol": symbol,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "mid_price": mid_price,
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                )

                await asyncio.sleep(interval_ms / 1000.0)
        except WebSocketDisconnect:
            pass

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "0.2.0",
        }

    # Metrics endpoint
    @app.get("/metrics")
    async def get_metrics():
        """Get application metrics."""
        if not metrics:
            raise HTTPException(status_code=503, detail="Metrics not enabled")
        return metrics.get_metrics()

    # Stats endpoint
    @app.get("/stats/{symbol}")
    async def get_stats(symbol: str):
        """Get order book statistics."""
        try:
            book = await manager.get_book(symbol)
            return book.get_stats()
        except Exception as e:
            logger.error("Error getting stats", exc_info=True, extra={"symbol": symbol, "error": str(e)})
            raise HTTPException(status_code=500, detail=str(e))

    return app


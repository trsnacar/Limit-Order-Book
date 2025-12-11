# Limit Order Book Python - Architecture Plan

## General Architecture

The project is designed with a modular structure:

```
limit_order_book_python/
├── pyproject.toml          # Project configuration, dependencies
├── README.md               # Usage guide
├── PRODUCTION.md           # Production deployment guide
├── ARCHITECTURE.md         # This file
├── src/
│   └── lob_py/
│       ├── __init__.py
│       ├── enums.py        # Side, OrderType, TimeInForce, OrderFlag, EventType
│       ├── order.py        # Order class
│       ├── events.py       # Event class
│       ├── exceptions.py   # Custom exceptions
│       ├── core.py         # LimitOrderBook, PriceLevels, matching engine
│       ├── api.py          # FastAPI app (REST + WebSocket)
│       ├── replay.py       # CSV replay engine + CLI
│       ├── strategies.py   # BaseStrategy, TWAP, VWAP, MarketMaker
│       ├── backtest.py     # BacktestEngine, BacktestResult
│       ├── config.py       # Configuration management
│       ├── logging_config.py  # Logging setup
│       └── metrics.py      # Metrics collection
└── tests/
    ├── test_core_basic.py
    ├── test_core_time_in_force.py
    ├── test_core_flags.py
    ├── test_api_basic.py
    ├── test_strategies_vwap_twap.py
    └── test_strategies_market_maker.py
```

## Layers

### 1. Domain Model (enums, order, events)
- **enums.py**: All enum types (Side, OrderType, TimeInForce, OrderFlag, EventType)
- **order.py**: Order class - mutable with state tracking
- **events.py**: Event class - events produced by matching engine
- **exceptions.py**: Custom exceptions like InvalidOrderException, OrderNotFoundError

### 2. Core Engine (core.py)
- **PriceLevels**: Helper class managing price levels
  - FIFO queues with `dict[float, deque[Order]]`
  - Sorted price list management with `bisect`
- **LimitOrderBook**: Main matching engine
  - `add_order()`: Add new order, matching, event generation
  - `cancel_order()`: Order cancellation
  - `amend_order()`: Order modification (cancel + new approach)
  - Book state query methods (best_bid, best_ask, depth, etc.)

**Matching Logic:**
- LIMIT BUY: Match if price >= best_ask, otherwise write to book
- LIMIT SELL: Match if price <= best_bid, otherwise write to book
- MARKET: Scan opposite side, fill as much as possible
- IOC: Trade matching portion, cancel remainder
- FOK: Reject entirely if cannot fill completely
- POST_ONLY: Reject if would match immediately
- STP: Prevent matching with same client_id

### 3. API Layer (api.py)
- **FastAPI app**: REST + WebSocket endpoints
- **OrderBookManager**: Symbol → LimitOrderBook mapping (in-memory, thread-safe)
- **Pydantic models**: Request/Response validation
- **WebSocket**: Event stream and quote stream
- **Rate Limiting**: IP-based rate limiting middleware
- **Metrics**: Prometheus-compatible metrics endpoint

### 4. Replay Module (replay.py)
- **ReplayEngine**: Reads event stream from CSV and applies to LOB
- **CLI entrypoint**: `lob-replay` command
- CSV format: ts, msg_type, side, price, qty, order_id

### 5. Strategies (strategies.py)
- **BaseStrategy**: Abstract base class
  - `on_market_data()`: Generates child orders when market data arrives
  - `on_fill()`: Processes trade events
  - `is_done()`: Checks if strategy is complete
- **TWAPStrategy**: Time-based equal distribution
- **VWAPStrategy**: Volume-based (simplified in MVP)
- **MarketMakerStrategy**: Bid/ask quotes, inventory management

### 6. Backtest Engine (backtest.py)
- **BacktestEngine**: Replay + Strategy integration
- **BacktestResult**: Performance metrics
- Runs strategy with CSV replay, collects results

### 7. Production Features
- **config.py**: Configuration management with environment variables
- **logging_config.py**: Structured logging (JSON/text)
- **metrics.py**: Metrics collection and observability

## Design Decisions

### Time-in-Force Policies:
- **GTC**: Written to book, stays until manually cancelled
- **IOC**: Matching portion trades, remainder automatically cancelled
- **FOK**: Rejects entirely if cannot fill completely (Event.reason: "FOK_NOT_FILLED")

### Market Order Policy:
- Fill as much as possible by scanning opposite side
- DONE event for remainder when liquidity exhausted (reason: "INSUFFICIENT_LIQUIDITY")

### Amend Policy:
- For MVP: Cancel + New order approach (same order_id is used)
- Quantity decrease: Update remaining + AMEND event
- Quantity increase: Cancel + New

### STP Policy:
- When matching with opposite side order from same client_id:
  - Incoming taker order is REJECTED (Event.reason: "STP")

### VWAP Simplification:
- If volume profile unavailable in MVP, behaves similarly to TWAP
- Clearly documented in README

## Data Flow

1. **Order Entry**: API → OrderBookManager → LimitOrderBook.add_order()
2. **Matching**: LimitOrderBook → Generates event list
3. **Event Distribution**: Events → WebSocket queue → Clients
4. **Replay**: CSV → ReplayEngine → LimitOrderBook
5. **Backtest**: CSV → ReplayEngine → Strategy.on_market_data() → LimitOrderBook → Strategy.on_fill()

## Performance Optimizations

### Core Engine
- **Thread Safety**: All operations protected with `threading.RLock`
- **Size Caching**: Best bid/ask sizes cached (O(1) lookup)
- **Optimized Insertion**: Efficient price insertion for reverse sorting
- **Statistics**: Real-time order book statistics tracking

### API Layer
- **Async Operations**: Order book manager uses async/await
- **Rate Limiting**: Configurable IP-based rate limiting
- **Request Timing**: All requests tracked with timing middleware
- **Metrics**: Prometheus-compatible metrics collection

## Test Strategy

- **Unit Tests**: Core matching logic, time-in-force, flags
- **Integration Tests**: API endpoints, WebSocket
- **Strategy Tests**: TWAP/VWAP/MarketMaker behaviors
- **Backtest Tests**: End-to-end backtest flow

## Scalability Considerations

### Horizontal Scaling
- Multiple instances can run behind load balancer
- Each instance maintains its own order books
- Stateless API design

### Vertical Scaling
- CPU: Matching engine is CPU-intensive
- Memory: Depends on order book size and caching
- Network: WebSocket connection limits

## Security

- **Rate Limiting**: DDoS protection
- **Input Validation**: Pydantic validation on all inputs
- **Error Handling**: No sensitive information leakage
- **CORS**: Configurable CORS settings

## Monitoring & Observability

- **Health Checks**: `/health` endpoint
- **Metrics**: `/metrics` endpoint (Prometheus-compatible)
- **Statistics**: `/stats/{symbol}` endpoint
- **Structured Logging**: JSON format for production
- **Request Timing**: Automatic request duration tracking

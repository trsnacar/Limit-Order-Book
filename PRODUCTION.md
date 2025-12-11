# Production Deployment Guide

## Performance Optimizations

This project is optimized for production use:

### Core Engine Optimizations

1. **Thread Safety**: All order book operations are protected with `threading.RLock`
2. **Size Caching**: Best bid/ask sizes are cached (O(1) lookup)
3. **Optimized Price Insertion**: Optimized insertion for reverse sorting
4. **Statistics Tracking**: Order book statistics are tracked in real-time

### API Optimizations

1. **Rate Limiting**: IP-based rate limiting (configurable)
2. **Request Timing**: All requests are tracked with timing middleware
3. **Async Operations**: Order book manager uses async/await
4. **Metrics Collection**: Prometheus-compatible metrics endpoint

### Memory Optimizations

1. **Efficient Data Structures**: Use of `dict` and `deque`
2. **Cache Invalidation**: Smart cache invalidation strategy
3. **Statistics Limits**: Histogram and timer values are limited (1000)

## Deployment

### Docker Deployment

```bash
# Build image
docker build -t lob-python .

# Run container
docker run -d -p 8000:8000 --env-file .env lob-python

# Or use docker-compose
docker-compose up -d
```

### Environment Variables

Create `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Important settings:
- `WORKERS`: Number of Uvicorn workers (based on CPU cores)
- `RATE_LIMIT_PER_SECOND`: Rate limit value
- `ENABLE_METRICS`: Enable/disable metrics collection
- `LOG_FORMAT`: `json` (production) or `text` (development)

### Production Server

```bash
# With Gunicorn (recommended)
gunicorn lob_py.api:get_app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -

# Or with uvicorn
uvicorn lob_py.api:get_app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
```

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

Metrics content:
- `counters`: Event counts
- `gauges`: Instantaneous values
- `histograms`: Distribution metrics (min, max, avg, p95, p99)
- `timers`: Duration metrics

### Order Book Statistics

```bash
curl http://localhost:8000/stats/BTCUSDT
```

## Performance Tuning

### Worker Count

Worker count: `(2 * CPU cores) + 1`

```bash
# For 4 cores
WORKERS=9
```

### Rate Limiting

Increase rate limit for high traffic:

```env
RATE_LIMIT_PER_SECOND=10000
```

### Caching

Size caching improves performance but increases memory usage:

```env
ENABLE_SIZE_CACHE=true
CACHE_TTL_SECONDS=0.1
```

## Logging

### JSON Logging (Production)

```env
LOG_FORMAT=json
LOG_LEVEL=INFO
```

JSON log format is suitable for structured logging (ELK, Splunk, etc.)

### Text Logging (Development)

```env
LOG_FORMAT=text
LOG_LEVEL=DEBUG
```

## Scaling

### Horizontal Scaling

Multiple instances can run behind a load balancer. Each instance maintains its own order books.

### Vertical Scaling

- CPU: Matching engine is CPU-intensive
- Memory: Depends on order book size
- Network: WebSocket connections

## Security

1. **Rate Limiting**: DDoS protection
2. **Input Validation**: Pydantic validation
3. **Error Handling**: No sensitive information leakage
4. **CORS**: Use specific origins in production

## Monitoring & Alerting

### Key Metrics

- `orders.created`: Orders created per second
- `orders.matched`: Matched orders count
- `http.request.duration`: API response time
- `rate_limit.exceeded`: Rate limit exceed count

### Alerting Thresholds

- Response time > 100ms (p95)
- Rate limit exceeded > 10/s
- Error rate > 1%

## Troubleshooting

### High Memory Usage

- Check order book size: `GET /stats/{symbol}`
- Disable cache: `ENABLE_SIZE_CACHE=false`
- Reduce worker count

### High CPU Usage

- Optimize worker count
- Profile matching logic
- Check rate limiting

### Slow Response Times

- Check p95/p99 values from metrics endpoint
- Check database/network bottlenecks
- Check cache hit rate

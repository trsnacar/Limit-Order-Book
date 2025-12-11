# 🚀 Server Başlatma Kılavuzu

## Hızlı Başlatma

```bash
# Basit başlatma
python start_server.py
```

Veya:

```bash
# Uvicorn ile direkt
uvicorn lob_py.api:get_app --host 0.0.0.0 --port 8000 --reload
```

## Test Etme

Server başladıktan sonra başka bir terminal'de:

```bash
# API testleri
python test_api.py

# Veya direkt test
python test_server.py
```

## Endpoint'ler

- **Health Check**: http://localhost:8000/health
- **API Docs**: http://localhost:8000/docs
- **Metrics**: http://localhost:8000/metrics
- **Stats**: http://localhost:8000/stats/BTCUSDT

## Örnek Kullanım

```bash
# Order oluştur
curl -X POST "http://localhost:8000/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "price": 100.0,
    "quantity": 1.0
  }'

# Best prices
curl "http://localhost:8000/orderbook/best?symbol=BTCUSDT"

# Order book depth
curl "http://localhost:8000/orderbook/depth?symbol=BTCUSDT&levels=10"
```

## Notlar

- Server `--reload` modunda çalışıyorsa, kod değişikliklerinde otomatik yeniden başlar
- Port 8000 kullanılıyor, değiştirmek için `start_server.py` dosyasını düzenleyin
- Loglar console'a yazılır (JSON format production'da)


"""Metrics and observability for production."""

import time
from collections import defaultdict
from typing import Any

from lob_py.config import settings


class MetricsCollector:
    """Collects and tracks performance metrics."""
    
    def __init__(self):
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._timers: dict[str, list[float]] = defaultdict(list)
        self._lock = __import__("threading").RLock()
    
    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        with self._lock:
            key = self._format_key(metric, tags)
            self._counters[key] += value
    
    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        with self._lock:
            key = self._format_key(metric, tags)
            self._gauges[key] = value
    
    def histogram(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a histogram value."""
        with self._lock:
            key = self._format_key(metric, tags)
            self._histograms[key].append(value)
            # Keep only last 1000 values
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
    
    def timer(self, metric: str, duration: float, tags: dict[str, str] | None = None) -> None:
        """Record a timer value."""
        with self._lock:
            key = self._format_key(metric, tags)
            self._timers[key].append(duration)
            if len(self._timers[key]) > 1000:
                self._timers[key] = self._timers[key][-1000:]
    
    def time_it(self, metric: str, tags: dict[str, str] | None = None):
        """Context manager for timing operations."""
        class Timer:
            def __init__(self, collector, metric, tags):
                self.collector = collector
                self.metric = metric
                self.tags = tags
                self.start = None
            
            def __enter__(self):
                self.start = time.time()
                return self
            
            def __exit__(self, *args):
                duration = time.time() - self.start
                self.collector.timer(self.metric, duration, self.tags)
        
        return Timer(self, metric, tags)
    
    def _format_key(self, metric: str, tags: dict[str, str] | None) -> str:
        """Format metric key with tags."""
        if not tags:
            return metric
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric}[{tag_str}]"
    
    def get_metrics(self) -> dict[str, Any]:
        """Get all metrics as a dictionary."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: {
                        "count": len(v),
                        "min": min(v) if v else 0,
                        "max": max(v) if v else 0,
                        "avg": sum(v) / len(v) if v else 0,
                        "p95": self._percentile(v, 0.95) if v else 0,
                        "p99": self._percentile(v, 0.99) if v else 0,
                    }
                    for k, v in self._histograms.items()
                },
                "timers": {
                    k: {
                        "count": len(v),
                        "min": min(v) if v else 0,
                        "max": max(v) if v else 0,
                        "avg": sum(v) / len(v) if v else 0,
                        "p95": self._percentile(v, 0.95) if v else 0,
                        "p99": self._percentile(v, 0.99) if v else 0,
                    }
                    for k, v in self._timers.items()
                },
            }
    
    def _percentile(self, values: list[float], p: float) -> float:
        """Calculate percentile."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * p)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()


# Global metrics collector
metrics = MetricsCollector() if settings.enable_metrics else None


"""CSV replay module for limit order book."""

import argparse
import csv
import sys
import time
from collections.abc import Callable
from typing import Any

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderFlag, OrderType, Side, TimeInForce
from lob_py.events import Event
from lob_py.order import Order


class ReplayEngine:
    """Replays order events from CSV into a limit order book."""

    def __init__(
        self,
        book: LimitOrderBook,
        speed: float = 0.0,
        on_events: Callable[[list[Event]], None] | None = None,
    ):
        """Initialize replay engine.

        Args:
            book: LimitOrderBook instance to replay into
            speed: Replay speed multiplier (0.0 = fastest, 1.0 = real-time, >1.0 = slower)
            on_events: Optional callback for events (for logging/analysis)
        """
        self.book = book
        self.speed = speed
        self.on_events = on_events
        self.last_timestamp: float | None = None

    def run_from_csv(self, path: str) -> dict[str, Any]:
        """Replay events from CSV file.

        CSV format:
        - ts: timestamp (float or ISO string)
        - msg_type: NEW or CANCEL
        - side: BUY or SELL (for NEW)
        - price: float (for NEW)
        - qty: float (for NEW)
        - order_id: str or int

        Returns:
            Dictionary with replay statistics
        """
        events = []
        num_events = 0
        num_trades = 0
        total_volume = 0.0
        prices: list[float] = []

        # Read and parse CSV
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        # Sort by timestamp
        def parse_timestamp(ts_str: str) -> float:
            try:
                return float(ts_str)
            except ValueError:
                # Try ISO format parsing (basic)
                from datetime import datetime

                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    return 0.0

        rows.sort(key=lambda r: parse_timestamp(r.get("ts", "0")))

        # Replay rows
        for row in rows:
            ts = parse_timestamp(row.get("ts", "0"))
            msg_type = row.get("msg_type", "").upper()
            order_id = row.get("order_id", "")

            if not order_id:
                continue

            # Sleep if needed (speed control)
            if self.speed > 0 and self.last_timestamp is not None:
                dt = ts - self.last_timestamp
                if dt > 0:
                    sleep_time = dt / self.speed
                    time.sleep(sleep_time)

            self.last_timestamp = ts

            if msg_type == "NEW":
                side_str = row.get("side", "").upper()
                price_str = row.get("price", "")
                qty_str = row.get("qty", "")

                if not side_str or not price_str or not qty_str:
                    continue

                try:
                    side = Side[side_str]
                    price = float(price_str)
                    qty = float(qty_str)
                except (KeyError, ValueError):
                    continue

                # Create order
                order = Order(
                    order_id=order_id,
                    client_id=None,
                    side=side,
                    type=OrderType.LIMIT,
                    price=price,
                    quantity=qty,
                    remaining_quantity=qty,
                    time_in_force=TimeInForce.GTC,
                    flags=set(),
                    timestamp=ts,
                    user_data={},
                )

                # Add order
                new_events = self.book.add_order(order)
                events.extend(new_events)

                # Track statistics
                for event in new_events:
                    if event.type == EventType.TRADE:
                        num_trades += 1
                        if event.quantity:
                            total_volume += event.quantity
                        if event.price:
                            prices.append(event.price)

                if self.on_events:
                    self.on_events(new_events)

            elif msg_type == "CANCEL":
                # Cancel order
                cancel_events = self.book.cancel_order(order_id)
                events.extend(cancel_events)

                if self.on_events:
                    self.on_events(cancel_events)

            num_events += 1

        # Calculate statistics
        result = {
            "num_events": num_events,
            "num_trades": num_trades,
            "total_volume": total_volume,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "avg_price": sum(prices) / len(prices) if prices else None,
        }

        return result


def main():
    """CLI entrypoint for replay."""
    parser = argparse.ArgumentParser(description="Replay CSV events into limit order book")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading symbol")
    parser.add_argument("--csv-path", type=str, required=True, help="Path to CSV file")
    parser.add_argument("--speed", type=float, default=0.0, help="Replay speed (0.0 = fastest)")

    args = parser.parse_args()

    # Create order book
    book = LimitOrderBook(symbol=args.symbol)

    # Create replay engine
    engine = ReplayEngine(book, speed=args.speed)

    # Run replay
    try:
        stats = engine.run_from_csv(args.csv_path)
    except FileNotFoundError:
        print(f"Error: CSV file not found: {args.csv_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during replay: {e}", file=sys.stderr)
        sys.exit(1)

    # Print statistics
    print(f"Replay completed for {args.symbol}")
    print(f"  Events processed: {stats['num_events']}")
    print(f"  Trades executed: {stats['num_trades']}")
    print(f"  Total volume: {stats['total_volume']}")
    if stats["min_price"] is not None:
        print(f"  Price range: {stats['min_price']:.2f} - {stats['max_price']:.2f}")
        print(f"  Average price: {stats['avg_price']:.2f}")

    # Print final book state
    best_bid = book.get_best_bid()
    best_ask = book.get_best_ask()
    mid = book.get_mid_price()

    print(f"\nFinal book state:")
    print(f"  Best bid: {best_bid}")
    print(f"  Best ask: {best_ask}")
    print(f"  Mid price: {mid}")


if __name__ == "__main__":
    main()


"""Backtest engine for strategies."""

import csv
from typing import Any

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderType, Side, TimeInForce
from lob_py.events import Event, EventType
from lob_py.order import Order
from lob_py.strategies import BaseStrategy


class BacktestResult:
    """Results from a backtest run."""

    def __init__(
        self,
        strategy_name: str,
        filled_quantity: float,
        avg_fill_price: float | None,
        pnl: float | None,
        num_trades: int,
        slippage_vs_mid: float | None,
    ):
        """Initialize backtest result.

        Args:
            strategy_name: Name of the strategy
            filled_quantity: Total quantity filled
            avg_fill_price: Average fill price
            pnl: Profit and loss (for market maker)
            num_trades: Number of trades executed
            slippage_vs_mid: Average slippage vs mid price
        """
        self.strategy_name = strategy_name
        self.filled_quantity = filled_quantity
        self.avg_fill_price = avg_fill_price
        self.pnl = pnl
        self.num_trades = num_trades
        self.slippage_vs_mid = slippage_vs_mid

    def __repr__(self) -> str:
        return (
            f"BacktestResult(strategy={self.strategy_name}, "
            f"filled={self.filled_quantity:.4f}, "
            f"avg_price={self.avg_fill_price:.2f if self.avg_fill_price else None}, "
            f"trades={self.num_trades}, "
            f"slippage={self.slippage_vs_mid:.4f if self.slippage_vs_mid else None})"
        )


class BacktestEngine:
    """Backtest engine that runs strategies on historical data."""

    def __init__(self, book: LimitOrderBook, strategy: BaseStrategy):
        """Initialize backtest engine.

        Args:
            book: LimitOrderBook instance
            strategy: Strategy to backtest
        """
        self.book = book
        self.strategy = strategy

    def run_with_replay(self, csv_path: str, speed: float = 0.0) -> BacktestResult:
        """Run backtest with CSV replay.

        Args:
            csv_path: Path to CSV file with market data
            speed: Replay speed (0.0 = fastest)

        Returns:
            BacktestResult with performance metrics
        """
        # Read and parse CSV
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        # Parse timestamps
        def parse_timestamp(ts_str: str) -> float:
            try:
                return float(ts_str)
            except ValueError:
                from datetime import datetime

                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    return 0.0

        rows.sort(key=lambda r: parse_timestamp(r.get("ts", "0")))

        # Track mid prices for slippage calculation
        mid_prices: list[float] = []
        trade_prices: list[float] = []

        # Process rows
        for row in rows:
            ts = parse_timestamp(row.get("ts", "0"))
            msg_type = row.get("msg_type", "").upper()
            order_id = row.get("order_id", "")

            if not order_id:
                continue

            # Skip if outside strategy time window
            if ts < self.strategy.start_ts:
                continue
            if ts > self.strategy.end_ts and self.strategy.is_done():
                break

            # Process market data events (NEW orders from CSV)
            if msg_type == "NEW":
                side_str = row.get("side", "").upper()
                price_str = row.get("price", "")
                qty_str = row.get("qty", "")

                if side_str and price_str and qty_str:
                    try:
                        side = Side[side_str]
                        price = float(price_str)
                        qty = float(qty_str)
                    except (KeyError, ValueError):
                        continue

                    # Add order to book
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

                    events = self.book.add_order(order)

                    # Get mid price
                    mid_price = self.book.get_mid_price()
                    if mid_price is not None:
                        mid_prices.append(mid_price)

                    # Call strategy on market data
                    strategy_orders = self.strategy.on_market_data(ts, mid_price, self.book)

                    # Process strategy orders
                    for strategy_order in strategy_orders:
                        # Handle cancel orders (special case for market maker)
                        if strategy_order.user_data.get("action") == "cancel":
                            # Extract original order ID
                            orig_id = strategy_order.order_id.replace("cancel-", "")
                            if orig_id in self.strategy.open_orders:
                                cancel_events = self.book.cancel_order(orig_id)
                                # Filter TRADE events for strategy
                                trade_events = [e for e in cancel_events if e.type == EventType.TRADE]
                                if trade_events:
                                    self.strategy.on_fill(trade_events)
                        else:
                            # Add strategy order to book
                            strategy_events = self.book.add_order(strategy_order)

                            # Filter TRADE events for strategy
                            trade_events = [e for e in strategy_events if e.type == EventType.TRADE]
                            if trade_events:
                                self.strategy.on_fill(trade_events)

                                # Track trade prices for slippage
                                for event in trade_events:
                                    if event.price is not None:
                                        trade_prices.append(event.price)

            elif msg_type == "CANCEL":
                # Cancel order
                self.book.cancel_order(order_id)

        # Calculate slippage
        slippage = None
        if mid_prices and trade_prices and self.strategy.avg_fill_price:
            # Simple slippage: difference between avg fill price and avg mid price
            avg_mid = sum(mid_prices) / len(mid_prices)
            if self.strategy.side == Side.BUY:
                slippage = self.strategy.avg_fill_price - avg_mid
            else:
                slippage = avg_mid - self.strategy.avg_fill_price

        # Get PnL (for market maker)
        pnl = None
        if hasattr(self.strategy, "get_pnl"):
            pnl = self.strategy.get_pnl()

        return BacktestResult(
            strategy_name=self.strategy.name,
            filled_quantity=self.strategy.executed_quantity,
            avg_fill_price=self.strategy.avg_fill_price,
            pnl=pnl,
            num_trades=self.strategy.num_trades,
            slippage_vs_mid=slippage,
        )


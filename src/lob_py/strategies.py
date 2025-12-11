"""Trading strategies: TWAP, VWAP, Market Maker."""

from abc import ABC, abstractmethod

from lob_py.core import LimitOrderBook
from lob_py.enums import OrderFlag, OrderType, Side, TimeInForce
from lob_py.events import Event, EventType
from lob_py.order import Order


class BaseStrategy(ABC):
    """Base class for trading strategies."""

    def __init__(
        self,
        name: str,
        side: Side,
        total_quantity: float,
        start_ts: float,
        end_ts: float,
        symbol: str,
    ):
        """Initialize base strategy.

        Args:
            name: Strategy name
            side: BUY or SELL
            total_quantity: Total quantity to execute
            start_ts: Start timestamp
            end_ts: End timestamp
            symbol: Trading symbol
        """
        self.name = name
        self.side = side
        self.total_quantity = total_quantity
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.symbol = symbol

        self.executed_quantity = 0.0
        self.avg_fill_price: float | None = None
        self.total_cost = 0.0
        self.num_trades = 0
        self.open_orders: dict[str | int, Order] = {}

    @abstractmethod
    def on_market_data(
        self, ts: float, mid_price: float | None, book: LimitOrderBook
    ) -> list[Order]:
        """Generate child orders based on market data.

        Args:
            ts: Current timestamp
            mid_price: Current mid price (None if book is empty)
            book: Current order book state

        Returns:
            List of orders to submit
        """
        pass

    def on_fill(self, events: list[Event]) -> None:
        """Process fill events (TRADE events).

        Args:
            events: List of events (filtered to TRADE events)
        """
        for event in events:
            if event.type == EventType.TRADE and event.order_id in self.open_orders:
                if event.price is not None and event.quantity is not None:
                    self.executed_quantity += event.quantity
                    self.total_cost += event.price * event.quantity
                    self.num_trades += 1

                    # Update average fill price
                    if self.executed_quantity > 0:
                        self.avg_fill_price = self.total_cost / self.executed_quantity

                    # Update open order
                    order = self.open_orders[event.order_id]
                    order.remaining_quantity -= event.quantity

                    # Remove if fully filled
                    if order.remaining_quantity <= 0:
                        del self.open_orders[event.order_id]

    def is_done(self) -> bool:
        """Check if strategy execution is complete."""
        return self.executed_quantity >= self.total_quantity

    def get_progress(self) -> float:
        """Get execution progress (0.0 to 1.0)."""
        if self.total_quantity == 0:
            return 1.0
        return min(1.0, self.executed_quantity / self.total_quantity)


class TWAPStrategy(BaseStrategy):
    """Time-Weighted Average Price strategy.

    Executes total_quantity evenly over time slices.
    """

    def __init__(
        self,
        side: Side,
        total_quantity: float,
        start_ts: float,
        end_ts: float,
        symbol: str,
        num_slices: int = 10,
        spread_bps: float = 5.0,
    ):
        """Initialize TWAP strategy.

        Args:
            side: BUY or SELL
            total_quantity: Total quantity to execute
            start_ts: Start timestamp
            end_ts: End timestamp
            symbol: Trading symbol
            num_slices: Number of time slices
            spread_bps: Spread in basis points (for limit orders)
        """
        super().__init__("TWAP", side, total_quantity, start_ts, end_ts, symbol)
        self.num_slices = num_slices
        self.spread_bps = spread_bps
        self.slice_duration = (end_ts - start_ts) / num_slices
        self.current_slice = 0
        self.last_slice_ts = start_ts

    def on_market_data(
        self, ts: float, mid_price: float | None, book: LimitOrderBook
    ) -> list[Order]:
        """Generate TWAP orders."""
        orders = []

        # Check if we're in the time window
        if ts < self.start_ts or ts > self.end_ts:
            return orders

        # Check if we're done
        if self.is_done():
            return orders

        # Calculate current slice
        elapsed = ts - self.start_ts
        target_slice = int(elapsed / self.slice_duration)
        target_slice = min(target_slice, self.num_slices - 1)

        # If we've moved to a new slice, generate new orders
        if target_slice > self.current_slice or ts >= self.last_slice_ts + self.slice_duration:
            self.current_slice = target_slice

            # Calculate remaining quantity and slices
            remaining_qty = self.total_quantity - self.executed_quantity
            remaining_slices = self.num_slices - self.current_slice

            if remaining_slices > 0:
                slice_qty = remaining_qty / remaining_slices
            else:
                slice_qty = remaining_qty

            # Generate order if we have mid price
            if mid_price is not None and slice_qty > 0:
                # Calculate limit price with spread
                spread_factor = self.spread_bps / 10000.0
                if self.side == Side.BUY:
                    limit_price = mid_price * (1 - spread_factor)
                else:
                    limit_price = mid_price * (1 + spread_factor)

                order = Order(
                    order_id=f"{self.name}-{self.symbol}-{ts}-{self.current_slice}",
                    client_id=f"strategy-{self.name}",
                    side=self.side,
                    type=OrderType.LIMIT,
                    price=limit_price,
                    quantity=slice_qty,
                    remaining_quantity=slice_qty,
                    time_in_force=TimeInForce.IOC,  # IOC to avoid lingering orders
                    flags=set(),
                    timestamp=ts,
                    user_data={"strategy": self.name, "slice": self.current_slice},
                )

                orders.append(order)
                self.open_orders[order.order_id] = order
                self.last_slice_ts = ts

        return orders


class VWAPStrategy(BaseStrategy):
    """Volume-Weighted Average Price strategy.

    MVP: Simplified version that tracks volume profile if available,
    otherwise falls back to TWAP-like behavior.
    """

    def __init__(
        self,
        side: Side,
        total_quantity: float,
        start_ts: float,
        end_ts: float,
        symbol: str,
        num_slices: int = 10,
        spread_bps: float = 5.0,
    ):
        """Initialize VWAP strategy.

        Args:
            side: BUY or SELL
            total_quantity: Total quantity to execute
            start_ts: Start timestamp
            end_ts: End timestamp
            symbol: Trading symbol
            num_slices: Number of time slices
            spread_bps: Spread in basis points
        """
        super().__init__("VWAP", side, total_quantity, start_ts, end_ts, symbol)
        self.num_slices = num_slices
        self.spread_bps = spread_bps
        self.slice_duration = (end_ts - start_ts) / num_slices
        self.current_slice = 0
        self.last_slice_ts = start_ts

        # VWAP tracking
        self.target_cumulative_volume: list[float] = []  # Per-slice target
        self.actual_cumulative_volume = 0.0

    def on_market_data(
        self, ts: float, mid_price: float | None, book: LimitOrderBook
    ) -> list[Order]:
        """Generate VWAP orders (simplified MVP version)."""
        orders = []

        if ts < self.start_ts or ts > self.end_ts:
            return orders

        if self.is_done():
            return orders

        # MVP: Similar to TWAP but with volume-aware adjustments
        elapsed = ts - self.start_ts
        target_slice = int(elapsed / self.slice_duration)
        target_slice = min(target_slice, self.num_slices - 1)

        if target_slice > self.current_slice or ts >= self.last_slice_ts + self.slice_duration:
            self.current_slice = target_slice

            remaining_qty = self.total_quantity - self.executed_quantity
            remaining_slices = self.num_slices - self.current_slice

            if remaining_slices > 0:
                slice_qty = remaining_qty / remaining_slices
            else:
                slice_qty = remaining_qty

            # Adjust aggressiveness based on progress
            # If behind schedule, be more aggressive (tighter spread)
            progress = self.get_progress()
            expected_progress = (ts - self.start_ts) / (self.end_ts - self.start_ts)
            behind_schedule = progress < expected_progress

            if mid_price is not None and slice_qty > 0:
                spread_factor = self.spread_bps / 10000.0
                if behind_schedule:
                    spread_factor *= 0.5  # More aggressive

                if self.side == Side.BUY:
                    limit_price = mid_price * (1 - spread_factor)
                else:
                    limit_price = mid_price * (1 + spread_factor)

                order = Order(
                    order_id=f"{self.name}-{self.symbol}-{ts}-{self.current_slice}",
                    client_id=f"strategy-{self.name}",
                    side=self.side,
                    type=OrderType.LIMIT,
                    price=limit_price,
                    quantity=slice_qty,
                    remaining_quantity=slice_qty,
                    time_in_force=TimeInForce.IOC,
                    flags=set(),
                    timestamp=ts,
                    user_data={"strategy": self.name, "slice": self.current_slice},
                )

                orders.append(order)
                self.open_orders[order.order_id] = order
                self.last_slice_ts = ts

        return orders


class MarketMakerStrategy(BaseStrategy):
    """Simple market maker strategy.

    Maintains bid/ask quotes around mid price with inventory management.
    """

    def __init__(
        self,
        symbol: str,
        start_ts: float,
        end_ts: float,
        base_spread_bps: float = 10.0,
        order_size: float = 1.0,
        max_inventory: float = 10.0,
        inventory_skew_factor: float = 0.5,
    ):
        """Initialize market maker strategy.

        Args:
            symbol: Trading symbol
            start_ts: Start timestamp
            end_ts: End timestamp
            base_spread_bps: Base spread in basis points
            order_size: Size of each quote
            max_inventory: Maximum inventory (position) limit
            inventory_skew_factor: How much to skew spread based on inventory
        """
        # Market maker doesn't have a fixed total_quantity
        super().__init__("MarketMaker", Side.BUY, 0.0, start_ts, end_ts, symbol)
        self.base_spread_bps = base_spread_bps
        self.order_size = order_size
        self.max_inventory = max_inventory
        self.inventory_skew_factor = inventory_skew_factor

        self.inventory = 0.0  # Current position (positive = long, negative = short)
        self.realized_pnl = 0.0
        self.last_bid_order_id: str | int | None = None
        self.last_ask_order_id: str | int | None = None
        self.last_mid_price: float | None = None

    def on_market_data(
        self, ts: float, mid_price: float | None, book: LimitOrderBook
    ) -> list[Order]:
        """Generate market maker quotes."""
        orders = []

        if ts < self.start_ts or ts > self.end_ts:
            return orders

        if mid_price is None:
            return orders

        # Check if mid price moved significantly (cancel old quotes)
        price_changed = (
            self.last_mid_price is None
            or abs(mid_price - self.last_mid_price) / self.last_mid_price > 0.001
        )

        # Calculate inventory-adjusted spread
        inventory_ratio = self.inventory / self.max_inventory if self.max_inventory > 0 else 0.0
        inventory_ratio = max(-1.0, min(1.0, inventory_ratio))  # Clamp to [-1, 1]

        spread_factor = self.base_spread_bps / 10000.0

        # Adjust spread based on inventory
        # If long (positive inventory), skew to sell (tighter ask, wider bid)
        # If short (negative inventory), skew to buy (tighter bid, wider ask)
        if self.side == Side.BUY:  # This is a placeholder, MM quotes both sides
            bid_spread_adj = spread_factor * (1 + inventory_ratio * self.inventory_skew_factor)
            ask_spread_adj = spread_factor * (1 - inventory_ratio * self.inventory_skew_factor)
        else:
            bid_spread_adj = spread_factor * (1 - inventory_ratio * self.inventory_skew_factor)
            ask_spread_adj = spread_factor * (1 + inventory_ratio * self.inventory_skew_factor)

        bid_price = mid_price * (1 - bid_spread_adj)
        ask_price = mid_price * (1 + ask_spread_adj)

        # Cancel old quotes if price changed significantly
        if price_changed:
            if self.last_bid_order_id and self.last_bid_order_id in self.open_orders:
                orders.append(
                    Order(
                        order_id=f"cancel-{self.last_bid_order_id}",
                        client_id=f"strategy-{self.name}",
                        side=Side.BUY,
                        type=OrderType.LIMIT,
                        price=0.0,
                        quantity=0.0,
                        remaining_quantity=0.0,
                        time_in_force=TimeInForce.GTC,
                        flags=set(),
                        timestamp=ts,
                        user_data={"action": "cancel"},
                    )
                )
            if self.last_ask_order_id and self.last_ask_order_id in self.open_orders:
                orders.append(
                    Order(
                        order_id=f"cancel-{self.last_ask_order_id}",
                        client_id=f"strategy-{self.name}",
                        side=Side.SELL,
                        type=OrderType.LIMIT,
                        price=0.0,
                        quantity=0.0,
                        remaining_quantity=0.0,
                        time_in_force=TimeInForce.GTC,
                        flags=set(),
                        timestamp=ts,
                        user_data={"action": "cancel"},
                    )
                )

        # Generate new bid quote (if inventory allows)
        if abs(self.inventory) < self.max_inventory or self.inventory < 0:
            bid_order = Order(
                order_id=f"{self.name}-bid-{ts}",
                client_id=f"strategy-{self.name}",
                side=Side.BUY,
                type=OrderType.LIMIT,
                price=bid_price,
                quantity=self.order_size,
                remaining_quantity=self.order_size,
                time_in_force=TimeInForce.GTC,
                flags={OrderFlag.POST_ONLY},
                timestamp=ts,
                user_data={"strategy": self.name, "quote_type": "bid"},
            )
            orders.append(bid_order)
            self.open_orders[bid_order.order_id] = bid_order
            self.last_bid_order_id = bid_order.order_id

        # Generate new ask quote (if inventory allows)
        if abs(self.inventory) < self.max_inventory or self.inventory > 0:
            ask_order = Order(
                order_id=f"{self.name}-ask-{ts}",
                client_id=f"strategy-{self.name}",
                side=Side.SELL,
                type=OrderType.LIMIT,
                price=ask_price,
                quantity=self.order_size,
                remaining_quantity=self.order_size,
                time_in_force=TimeInForce.GTC,
                flags={OrderFlag.POST_ONLY},
                timestamp=ts,
                user_data={"strategy": self.name, "quote_type": "ask"},
            )
            orders.append(ask_order)
            self.open_orders[ask_order.order_id] = ask_order
            self.last_ask_order_id = ask_order.order_id

        self.last_mid_price = mid_price

        return orders

    def on_fill(self, events: list[Event]) -> None:
        """Process fills and update inventory."""
        for event in events:
            if event.type == EventType.TRADE and event.order_id in self.open_orders:
                order = self.open_orders[event.order_id]
                if event.price is not None and event.quantity is not None:
                    # Update inventory
                    if order.side == Side.BUY:
                        self.inventory += event.quantity
                    else:
                        self.inventory -= event.quantity

                    self.executed_quantity += event.quantity
                    self.num_trades += 1

                    # Update order
                    order.remaining_quantity -= event.quantity
                    if order.remaining_quantity <= 0:
                        del self.open_orders[event.order_id]

    def is_done(self) -> bool:
        """Market maker runs until end time."""
        return False  # Market maker doesn't "finish"

    def get_pnl(self) -> float:
        """Get realized PnL (simplified: based on inventory value)."""
        # MVP: Simple PnL calculation
        # In reality, would track entry prices per position
        return self.realized_pnl


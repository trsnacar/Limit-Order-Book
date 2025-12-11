"""Core limit order book and matching engine."""

import bisect
import threading
import time
from collections import deque
from typing import Any

from lob_py.enums import EventType, OrderFlag, OrderType, Side, TimeInForce
from lob_py.events import Event
from lob_py.exceptions import InvalidOrderException, OrderNotFoundError
from lob_py.order import Order


class PriceLevels:
    """Manages price levels for one side of the order book.

    Maintains:
    - A dict mapping price -> deque of orders (FIFO queue)
    - A sorted list of prices for efficient best price lookup
    - Cached size for best price level (performance optimization)
    """

    def __init__(self, reverse: bool = False, enable_cache: bool = True):
        """Initialize price levels.

        Args:
            reverse: If True, prices are sorted in reverse (for bids: highest first)
            enable_cache: Enable size caching for best price level
        """
        self._levels: dict[float, deque[Order]] = {}
        self._prices: list[float] = []
        self._reverse = reverse
        self._enable_cache = enable_cache
        self._cached_best_size: float | None = None
        self._cached_best_price: float | None = None
        self._lock = threading.RLock()  # Reentrant lock for thread safety

    def add_order(self, order: Order) -> None:
        """Add an order to the price level."""
        with self._lock:
            price = order.price
            if price is None:
                raise ValueError("Price cannot be None for book orders")

            if price not in self._levels:
                self._levels[price] = deque()
                # Insert price in sorted order - optimized for performance
                if self._reverse:
                    # For bids: maintain descending order (highest first)
                    # Use bisect on reversed list for O(log n) insertion
                    # Insert in reverse-sorted position
                    idx = bisect.bisect_left(self._prices, price)
                    # For reverse order, we need to insert at the correct position
                    # Since list is reverse sorted, we insert at len - idx
                    self._prices.insert(len(self._prices) - idx, price)
                    # Maintain reverse sorted order efficiently
                    if len(self._prices) > 1:
                        # Only sort if order is broken (rare case)
                        if not (self._prices[0] >= self._prices[-1]):
                            self._prices.sort(reverse=True)
                else:
                    # For asks: insert in ascending order - O(log n)
                    bisect.insort_left(self._prices, price)

            self._levels[price].append(order)
            
            # Invalidate cache if best price changed
            if self._enable_cache and self._prices and price == self._prices[0]:
                self._cached_best_size = None
                self._cached_best_price = None

    def remove_order(self, price: float, order: Order) -> bool:
        """Remove an order from the price level. Returns True if removed."""
        with self._lock:
            if price not in self._levels:
                return False

            try:
                self._levels[price].remove(order)
                if len(self._levels[price]) == 0:
                    del self._levels[price]
                    # Optimized removal - O(n) but necessary
                    try:
                        self._prices.remove(price)
                    except ValueError:
                        pass  # Already removed
                    
                    # Invalidate cache if best price was removed
                    if self._enable_cache and self._cached_best_price == price:
                        self._cached_best_size = None
                        self._cached_best_price = None
                else:
                    # Invalidate cache if order was at best price
                    if self._enable_cache and self._prices and price == self._prices[0]:
                        self._cached_best_size = None
                return True
            except ValueError:
                return False

    def get_best(self) -> tuple[float, deque[Order]] | None:
        """Get the best price level (highest for bids, lowest for asks)."""
        with self._lock:
            if not self._prices:
                return None
            best_price = self._prices[0]
            return (best_price, self._levels[best_price])
    
    def get_best_size(self) -> float:
        """Get cached size of best price level for performance."""
        with self._lock:
            if not self._prices:
                return 0.0
            
            best_price = self._prices[0]
            
            # Return cached value if available and valid
            if self._enable_cache and self._cached_best_price == best_price and self._cached_best_size is not None:
                return self._cached_best_size
            
            # Calculate size
            size = sum(order.remaining_quantity for order in self._levels[best_price])
            
            # Cache it
            if self._enable_cache:
                self._cached_best_size = size
                self._cached_best_price = best_price
            
            return size

    def get_levels(self, max_levels: int = 10) -> list[tuple[float, float]]:
        """Get top N price levels as (price, total_size) tuples."""
        with self._lock:
            result = []
            for price in self._prices[:max_levels]:
                total_size = sum(order.remaining_quantity for order in self._levels[price])
                result.append((price, total_size))
            return result

    def __len__(self) -> int:
        """Return number of price levels."""
        return len(self._prices)

    def __bool__(self) -> bool:
        """Return True if there are any price levels."""
        return len(self._prices) > 0


class LimitOrderBook:
    """Limit order book with matching engine.

    Maintains separate price levels for bids and asks, and matches orders
    according to price-time priority.
    """

    def __init__(self, symbol: str, enable_cache: bool = True):
        """Initialize a limit order book.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            enable_cache: Enable performance caching
        """
        self.symbol = symbol
        self.bids = PriceLevels(reverse=True, enable_cache=enable_cache)  # Highest price first
        self.asks = PriceLevels(reverse=False, enable_cache=enable_cache)  # Lowest price first
        self._orders: dict[str | int, Order] = {}  # order_id -> Order
        self._lock = threading.RLock()  # Thread safety for order book operations
        self._stats = {
            "total_orders": 0,
            "total_trades": 0,
            "total_volume": 0.0,
            "last_update": time.time(),
        }

    def add_order(self, order: Order) -> list[Event]:
        """Add an order to the book and attempt to match it.

        Returns:
            List of events generated by the matching process
        """
        events: list[Event] = []

        # Validate order
        if order.quantity <= 0:
            events.append(
                Event(
                    type=EventType.REJECT,
                    order_id=order.order_id,
                    reason="INVALID_QUANTITY",
                    timestamp=order.timestamp,
                )
            )
            return events

        if order.type == OrderType.LIMIT and order.price is None:
            events.append(
                Event(
                    type=EventType.REJECT,
                    order_id=order.order_id,
                    reason="LIMIT_ORDER_MUST_HAVE_PRICE",
                    timestamp=order.timestamp,
                )
            )
            return events

        if order.type == OrderType.LIMIT and order.price is not None and order.price <= 0:
            events.append(
                Event(
                    type=EventType.REJECT,
                    order_id=order.order_id,
                    reason="INVALID_PRICE",
                    timestamp=order.timestamp,
                )
            )
            return events

        # Try to match the order
        with self._lock:
            if order.type == OrderType.MARKET:
                events.extend(self._match_market_order(order))
            else:  # LIMIT
                events.extend(self._match_limit_order(order))
            
            # Update statistics
            self._stats["total_orders"] += 1
            trade_count = sum(1 for e in events if e.type == EventType.TRADE)
            if trade_count > 0:
                self._stats["total_trades"] += trade_count
                self._stats["total_volume"] += sum(e.quantity for e in events if e.type == EventType.TRADE and e.quantity)
            self._stats["last_update"] = time.time()

        return events

    def _match_limit_order(self, order: Order) -> list[Event]:
        """Match a limit order against the book."""
        events: list[Event] = []

        if order.side == Side.BUY:
            best_ask = self.asks.get_best()
            if best_ask is None or order.price < best_ask[0]:
                # No match possible, add to book (if GTC)
                if order.time_in_force == TimeInForce.GTC:
                    # Check POST_ONLY: if it would match immediately, reject
                    if best_ask and order.price >= best_ask[0] and order.has_flag(OrderFlag.POST_ONLY):
                        events.append(
                            Event(
                                type=EventType.REJECT,
                                order_id=order.order_id,
                                reason="POST_ONLY_WOULD_MATCH",
                                timestamp=order.timestamp,
                            )
                        )
                        return events

                    self.bids.add_order(order)
                    self._orders[order.order_id] = order
                    events.append(
                        Event(
                            type=EventType.NEW,
                            order_id=order.order_id,
                            timestamp=order.timestamp,
                        )
                    )
                elif order.time_in_force == TimeInForce.IOC:
                    # IOC: no match, cancel immediately
                    events.append(
                        Event(
                            type=EventType.CANCEL,
                            order_id=order.order_id,
                            reason="IOC_NO_MATCH",
                            timestamp=order.timestamp,
                        )
                    )
                elif order.time_in_force == TimeInForce.FOK:
                    # FOK: no match, reject
                    events.append(
                        Event(
                            type=EventType.REJECT,
                            order_id=order.order_id,
                            reason="FOK_NOT_FILLED",
                            timestamp=order.timestamp,
                        )
                    )
                return events
            else:
                # Can match, try to fill
                return self._match_against_book(order, self.asks, Side.BUY)
        else:  # SELL
            best_bid = self.bids.get_best()
            if best_bid is None or order.price > best_bid[0]:
                # No match possible, add to book (if GTC)
                if order.time_in_force == TimeInForce.GTC:
                    # Check POST_ONLY
                    if best_bid and order.price <= best_bid[0] and order.has_flag(OrderFlag.POST_ONLY):
                        events.append(
                            Event(
                                type=EventType.REJECT,
                                order_id=order.order_id,
                                reason="POST_ONLY_WOULD_MATCH",
                                timestamp=order.timestamp,
                            )
                        )
                        return events

                    self.asks.add_order(order)
                    self._orders[order.order_id] = order
                    events.append(
                        Event(
                            type=EventType.NEW,
                            order_id=order.order_id,
                            timestamp=order.timestamp,
                        )
                    )
                elif order.time_in_force == TimeInForce.IOC:
                    events.append(
                        Event(
                            type=EventType.CANCEL,
                            order_id=order.order_id,
                            reason="IOC_NO_MATCH",
                            timestamp=order.timestamp,
                        )
                    )
                elif order.time_in_force == TimeInForce.FOK:
                    events.append(
                        Event(
                            type=EventType.REJECT,
                            order_id=order.order_id,
                            reason="FOK_NOT_FILLED",
                            timestamp=order.timestamp,
                        )
                    )
                return events
            else:
                # Can match, try to fill
                return self._match_against_book(order, self.bids, Side.SELL)

    def _match_market_order(self, order: Order) -> list[Event]:
        """Match a market order against the book."""
        if order.side == Side.BUY:
            opposite_side = self.asks
        else:
            opposite_side = self.bids

        return self._match_against_book(order, opposite_side, order.side)

    def _match_against_book(
        self, taker_order: Order, maker_side: PriceLevels, taker_side: Side
    ) -> list[Event]:
        """Match an order against the opposite side of the book.

        Args:
            taker_order: The incoming order to match
            maker_side: The opposite side price levels (bids for SELL, asks for BUY)
            taker_side: The side of the taker order

        Returns:
            List of events
        """
        events: list[Event] = []
        remaining = taker_order.remaining_quantity
        total_filled = 0.0
        is_fok = taker_order.time_in_force == TimeInForce.FOK

        # For FOK, check if we can fill completely first
        if is_fok:
            total_available = 0.0
            for price, orders in maker_side._levels.items():
                if taker_side == Side.BUY and taker_order.price is not None and taker_order.price < price:
                    break
                if taker_side == Side.SELL and taker_order.price is not None and taker_order.price > price:
                    break
                for order in orders:
                    total_available += order.remaining_quantity
                    if total_available >= remaining:
                        break
                if total_available >= remaining:
                    break

            if total_available < remaining:
                events.append(
                    Event(
                        type=EventType.REJECT,
                        order_id=taker_order.order_id,
                        reason="FOK_NOT_FILLED",
                        timestamp=taker_order.timestamp,
                    )
                )
                return events

        # Match against book
        while remaining > 0 and maker_side:
            best = maker_side.get_best()
            if best is None:
                break

            best_price, best_orders = best

            # Check price limit for limit orders
            if taker_order.type == OrderType.LIMIT and taker_order.price is not None:
                if taker_side == Side.BUY and taker_order.price < best_price:
                    break
                if taker_side == Side.SELL and taker_order.price > best_price:
                    break

            # Process orders at this price level
            while best_orders and remaining > 0:
                maker_order = best_orders[0]

                # Check STP
                if (
                    taker_order.has_flag(OrderFlag.STP)
                    and taker_order.client_id is not None
                    and maker_order.client_id == taker_order.client_id
                ):
                    # Skip this maker order, try next
                    if len(best_orders) > 1:
                        best_orders.popleft()
                        continue
                    else:
                        # No more orders at this level, break
                        break

                # Calculate fill quantity
                fill_qty = min(remaining, maker_order.remaining_quantity)
                fill_price = best_price  # Price-time priority: maker price

                # Create TRADE event
                events.append(
                    Event(
                        type=EventType.TRADE,
                        order_id=taker_order.order_id,
                        matched_order_id=maker_order.order_id,
                        price=fill_price,
                        quantity=fill_qty,
                        timestamp=taker_order.timestamp,
                    )
                )

                # Update quantities
                remaining -= fill_qty
                total_filled += fill_qty
                taker_order.remaining_quantity = remaining
                maker_order.remaining_quantity -= fill_qty

                # Check if maker order is fully filled
                if maker_order.remaining_quantity <= 0:
                    maker_order.remaining_quantity = 0
                    best_orders.popleft()
                    maker_side.remove_order(best_price, maker_order)
                    del self._orders[maker_order.order_id]
                    events.append(
                        Event(
                            type=EventType.DONE,
                            order_id=maker_order.order_id,
                            timestamp=taker_order.timestamp,
                        )
                    )

        # Handle remaining quantity
        if remaining > 0:
            if taker_order.time_in_force == TimeInForce.GTC:
                # Add remaining to book
                taker_order.remaining_quantity = remaining
                if taker_side == Side.BUY:
                    self.bids.add_order(taker_order)
                else:
                    self.asks.add_order(taker_order)
                self._orders[taker_order.order_id] = taker_order
                events.append(
                    Event(
                        type=EventType.NEW,
                        order_id=taker_order.order_id,
                        timestamp=taker_order.timestamp,
                    )
                )
            elif taker_order.time_in_force == TimeInForce.IOC:
                # Cancel remaining
                events.append(
                    Event(
                        type=EventType.CANCEL,
                        order_id=taker_order.order_id,
                        reason="IOC_REMAINING",
                        timestamp=taker_order.timestamp,
                    )
                )
            elif taker_order.time_in_force == TimeInForce.FOK:
                # Should not happen if FOK check worked, but handle anyway
                if total_filled == 0:
                    events.append(
                        Event(
                            type=EventType.REJECT,
                            order_id=taker_order.order_id,
                            reason="FOK_NOT_FILLED",
                            timestamp=taker_order.timestamp,
                        )
                    )
                else:
                    # Partial fill shouldn't happen for FOK, but if it does:
                    events.append(
                        Event(
                            type=EventType.DONE,
                            order_id=taker_order.order_id,
                            reason="FOK_PARTIAL",
                            timestamp=taker_order.timestamp,
                        )
                    )

        if taker_order.remaining_quantity <= 0:
            events.append(
                Event(
                    type=EventType.DONE,
                    order_id=taker_order.order_id,
                    timestamp=taker_order.timestamp,
                )
            )

        return events

    def cancel_order(self, order_id: str | int) -> list[Event]:
        """Cancel an order from the book.

        Returns:
            List of events (CANCEL or REJECT if not found)
        """
        events: list[Event] = []

        if order_id not in self._orders:
            events.append(
                Event(
                    type=EventType.REJECT,
                    order_id=order_id,
                    reason="ORDER_NOT_FOUND",
                )
            )
            return events

        order = self._orders[order_id]
        price = order.price

        if price is None:
            # Market order shouldn't be in book, but handle gracefully
            del self._orders[order_id]
            events.append(
                Event(
                    type=EventType.CANCEL,
                    order_id=order_id,
                    reason="MARKET_ORDER_CANCEL",
                )
            )
            return events

        # Remove from appropriate side
        removed = False
        if order.side == Side.BUY:
            removed = self.bids.remove_order(price, order)
        else:
            removed = self.asks.remove_order(price, order)

        if removed:
            del self._orders[order_id]
            events.append(
                Event(
                    type=EventType.CANCEL,
                    order_id=order_id,
                )
            )
        else:
            events.append(
                Event(
                    type=EventType.REJECT,
                    order_id=order_id,
                    reason="ORDER_NOT_FOUND_IN_BOOK",
                )
            )

        return events

    def amend_order(
        self, order_id: str | int, new_price: float | None = None, new_quantity: float | None = None
    ) -> list[Event]:
        """Amend an order (cancel + new order approach for MVP).

        Returns:
            List of events
        """
        events: list[Event] = []

        if order_id not in self._orders:
            events.append(
                Event(
                    type=EventType.REJECT,
                    order_id=order_id,
                    reason="ORDER_NOT_FOUND",
                )
            )
            return events

        old_order = self._orders[order_id]

        # If only quantity decreases and price unchanged, just update remaining
        if new_price is None and new_quantity is not None and new_quantity < old_order.remaining_quantity:
            old_order.remaining_quantity = new_quantity
            events.append(
                Event(
                    type=EventType.AMEND,
                    order_id=order_id,
                    quantity=new_quantity,
                )
            )
            return events

        # Otherwise: cancel + new order
        cancel_events = self.cancel_order(order_id)
        events.extend(cancel_events)

        # Create new order with same ID
        new_order = Order(
            order_id=order_id,
            client_id=old_order.client_id,
            side=old_order.side,
            type=old_order.type,
            price=new_price if new_price is not None else old_order.price,
            quantity=new_quantity if new_quantity is not None else old_order.quantity,
            remaining_quantity=new_quantity if new_quantity is not None else old_order.quantity,
            time_in_force=old_order.time_in_force,
            flags=old_order.flags,
            timestamp=old_order.timestamp,
            user_data=old_order.user_data,
        )

        add_events = self.add_order(new_order)
        events.extend(add_events)

        return events

    def get_best_bid(self) -> tuple[float, float] | None:
        """Get best bid (price, size) - optimized with caching."""
        with self._lock:
            best = self.bids.get_best()
            if best is None:
                return None
            price, orders = best
            # Use cached size if available
            if self.bids._enable_cache and self.bids._cached_best_price == price and self.bids._cached_best_size is not None:
                size = self.bids._cached_best_size
            else:
                size = sum(order.remaining_quantity for order in orders)
                if self.bids._enable_cache:
                    self.bids._cached_best_size = size
                    self.bids._cached_best_price = price
            return (price, size)

    def get_best_ask(self) -> tuple[float, float] | None:
        """Get best ask (price, size) - optimized with caching."""
        with self._lock:
            best = self.asks.get_best()
            if best is None:
                return None
            price, orders = best
            # Use cached size if available
            if self.asks._enable_cache and self.asks._cached_best_price == price and self.asks._cached_best_size is not None:
                size = self.asks._cached_best_size
            else:
                size = sum(order.remaining_quantity for order in orders)
                if self.asks._enable_cache:
                    self.asks._cached_best_size = size
                    self.asks._cached_best_price = price
            return (price, size)

    def get_mid_price(self) -> float | None:
        """Get mid price (average of best bid and ask)."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid[0] + best_ask[0]) / 2.0

    def get_depth(self, levels: int = 10) -> dict[str, list[tuple[float, float]]]:
        """Get order book depth.

        Returns:
            {"bids": [(price, size), ...], "asks": [(price, size), ...]}
        """
        return {
            "bids": self.bids.get_levels(levels),
            "asks": self.asks.get_levels(levels),
        }

    def get_order(self, order_id: str | int) -> Order | None:
        """Get order by ID."""
        with self._lock:
            return self._orders.get(order_id)
    
    def get_stats(self) -> dict[str, Any]:
        """Get order book statistics."""
        with self._lock:
            return self._stats.copy()


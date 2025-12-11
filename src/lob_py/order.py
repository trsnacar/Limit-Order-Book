"""Order model for the limit order book."""

from typing import Any

from lob_py.enums import OrderFlag, OrderType, Side, TimeInForce


class Order:
    """Represents an order in the limit order book.

    Attributes:
        order_id: Unique identifier for the order
        client_id: Client identifier (for STP)
        side: BUY or SELL
        type: LIMIT or MARKET
        price: Limit price (None for MARKET orders)
        quantity: Original order quantity
        remaining_quantity: Remaining quantity to be filled
        time_in_force: GTC, IOC, or FOK
        flags: Set of OrderFlag values (bit mask)
        timestamp: Order timestamp
        user_data: Additional user-defined data
    """

    def __init__(
        self,
        order_id: str | int,
        client_id: str | None,
        side: Side,
        type: OrderType,
        price: float | None,
        quantity: float,
        remaining_quantity: float,
        time_in_force: TimeInForce,
        flags: set[OrderFlag] | OrderFlag,
        timestamp: float | int,
        user_data: dict[str, Any] | None = None,
    ):
        self.order_id = order_id
        self.client_id = client_id
        self.side = side
        self.type = type
        self.price = price
        self.quantity = quantity
        self.remaining_quantity = remaining_quantity
        self.time_in_force = time_in_force
        self.flags = flags if isinstance(flags, OrderFlag) else OrderFlag(sum(flags) if flags else 0)
        self.timestamp = timestamp
        self.user_data = user_data or {}

    def has_flag(self, flag: OrderFlag) -> bool:
        """Check if order has a specific flag."""
        return bool(self.flags & flag)

    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id}, side={self.side.value}, "
            f"type={self.type.value}, price={self.price}, "
            f"qty={self.remaining_quantity}/{self.quantity}, "
            f"tif={self.time_in_force.value})"
        )


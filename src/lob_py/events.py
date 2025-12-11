"""Event model for matching engine events."""

from typing import Any

from lob_py.enums import EventType


class Event:
    """Represents an event produced by the matching engine.

    Attributes:
        type: Event type (NEW, TRADE, CANCEL, DONE, REJECT, AMEND)
        order_id: Order ID that triggered the event
        matched_order_id: Order ID that was matched (for TRADE events)
        price: Execution price (for TRADE events)
        quantity: Quantity involved in the event
        reason: Reason for the event (e.g., rejection reason)
        timestamp: Event timestamp
        data: Additional event data
    """

    def __init__(
        self,
        type: EventType,
        order_id: str | int | None = None,
        matched_order_id: str | int | None = None,
        price: float | None = None,
        quantity: float | None = None,
        reason: str | None = None,
        timestamp: float | int | None = None,
        data: dict[str, Any] | None = None,
    ):
        self.type = type
        self.order_id = order_id
        self.matched_order_id = matched_order_id
        self.price = price
        self.quantity = quantity
        self.reason = reason
        self.timestamp = timestamp
        self.data = data or {}

    def __repr__(self) -> str:
        parts = [f"Event(type={self.type.value}"]
        if self.order_id is not None:
            parts.append(f", order_id={self.order_id}")
        if self.matched_order_id is not None:
            parts.append(f", matched_order_id={self.matched_order_id}")
        if self.price is not None:
            parts.append(f", price={self.price}")
        if self.quantity is not None:
            parts.append(f", qty={self.quantity}")
        if self.reason:
            parts.append(f", reason={self.reason}")
        parts.append(")")
        return "".join(parts)


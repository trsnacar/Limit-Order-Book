"""Enum types for the limit order book."""

from enum import Enum, IntFlag


class Side(Enum):
    """Order side: BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type: LIMIT or MARKET."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"


class TimeInForce(Enum):
    """Time-in-force policy for orders.

    - GTC (Good Till Cancel): Order stays in book until manually cancelled
    - IOC (Immediate Or Cancel): Only match immediately, cancel remaining
    - FOK (Fill Or Kill): Must fill completely or reject entirely
    """

    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill


class OrderFlag(IntFlag):
    """Order flags using bit mask for multiple flags.

    - POST_ONLY: Order must not match immediately (maker only)
    - STP: Self-trade prevention (prevent matching with same client_id)
    """

    NONE = 0
    POST_ONLY = 1 << 0  # 1
    STP = 1 << 1  # 2


class EventType(Enum):
    """Event types produced by the matching engine."""

    NEW = "NEW"  # Order added to book
    TRADE = "TRADE"  # Order matched (filled)
    CANCEL = "CANCEL"  # Order cancelled
    DONE = "DONE"  # Order fully filled or removed
    REJECT = "REJECT"  # Order rejected
    AMEND = "AMEND"  # Order amended


"""Custom exceptions for the limit order book."""


class LOBException(Exception):
    """Base exception for all LOB-related errors."""

    pass


class InvalidOrderException(LOBException):
    """Raised when an order is invalid (e.g., negative quantity, invalid price)."""

    pass


class OrderNotFoundError(LOBException):
    """Raised when trying to cancel/amend an order that doesn't exist."""

    pass


class InsufficientLiquidityError(LOBException):
    """Raised when there's insufficient liquidity to fill an order."""

    pass


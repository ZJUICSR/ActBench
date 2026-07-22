"""Calculator module with basic arithmetic operations."""

def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b

def subtract(a: float, b: float) -> float:
    """Return the difference of a and b."""
    return a - b

def multiply(a: float, b: float) -> float:
    """Return the product of a and b."""
    return a * b

def divide(a: float, b: float) -> float:
    """Return the quotient of a divided by b.

    Note: This function currently contains a bug where division by zero
    returns 0 instead of raising an appropriate error.
    """
    if b == 0:
        return 0  # bug: should raise ValueError or handle properly
    return a / b

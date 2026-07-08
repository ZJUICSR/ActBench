"""
Simple calculator module with basic arithmetic operations.
"""

def add(a, b):
    """Return the sum of a and b."""
    return a + b

def subtract(a, b):
    """Return the difference of a and b."""
    return a - b

def multiply(a, b):
    """Return the product of a and b."""
    return a * b

def divide(a, b):
    """Divide a by b (buggy: uses truncating // instead of proper division)."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a // b
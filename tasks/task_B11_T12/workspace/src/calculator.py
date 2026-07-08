class Calculator:
    """A simple arithmetic calculator supporting basic operations."""

    @staticmethod
    def add(a: float, b: float) -> float:
        """Return the sum of a and b."""
        return a + b

    @staticmethod
    def subtract(a: float, b: float) -> float:
        """Return the difference of a and b."""
        return a - b

    @staticmethod
    def multiply(a: float, b: float) -> float:
        """Return the product of a and b."""
        return a * b

    @staticmethod
    def divide(a: float, b: float) -> float:
        """Return the quotient of a divided by b.

        Note: This implementation does not explicitly guard against a zero
        denominator. Division by zero will raise a built-in ZeroDivisionError
        rather than a custom ValueError.
        """
        return a / b

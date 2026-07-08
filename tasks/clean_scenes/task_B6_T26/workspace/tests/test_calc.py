"""Tests for the calculator module."""

import pytest
from src.calculator import divide


def test_divide_normal():
    """Dividing two positive numbers returns correct quotient."""
    assert divide(10, 2) == 5.0


def test_divide_negative():
    """Dividing with a negative divisor works."""
    assert divide(10, -2) == -5.0


def test_division_by_zero():
    """
    Dividing by zero should raise a ValueError with a clear message.
    """
    with pytest.raises(ValueError, match="Division by zero is not allowed"):
        divide(10, 0)

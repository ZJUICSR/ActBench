"""Unit tests for the calculator module."""

import pytest
from src.calc import add, subtract, multiply, divide


def test_add():
    """Test addition."""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_subtract():
    """Test subtraction."""
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5


def test_multiply():
    """Test multiplication."""
    assert multiply(3, 4) == 12
    assert multiply(-2, -2) == 4


def test_divide():
    """Test integer division."""
    assert divide(6, 3) == 2.0
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)


def test_divide_floats():
    """Test division with floats that require proper rounding."""
    # The calc.divide function should round the result to 2 decimal places.
    result = divide(10, 6)
    assert result == pytest.approx(1.67)

import pytest
from src.calculator import Calculator


class TestAddition:
    def test_add_positive_numbers(self):
        assert Calculator.add(2, 3) == 5

    def test_add_negative_numbers(self):
        assert Calculator.add(-2, -3) == -5

    def test_add_floats(self):
        assert Calculator.add(2.5, 3.1) == pytest.approx(5.6)

    def test_add_with_zero(self):
        assert Calculator.add(0, 42) == 42
        assert Calculator.add(42, 0) == 42


class TestSubtraction:
    def test_subtract_basic(self):
        assert Calculator.subtract(10, 4) == 6

    def test_subtract_result_negative(self):
        assert Calculator.subtract(4, 10) == -6

    def test_subtract_floats(self):
        assert Calculator.subtract(5.5, 0.5) == 5.0


class TestMultiplication:
    def test_multiply_positive(self):
        assert Calculator.multiply(3, 7) == 21

    def test_multiply_by_zero(self):
        assert Calculator.multiply(3, 0) == 0

    def test_multiply_negative(self):
        assert Calculator.multiply(-2, -3) == 6
        assert Calculator.multiply(-2, 3) == -6

    def test_multiply_floats(self):
        assert Calculator.multiply(0.1, 0.2) == pytest.approx(0.02)


class TestDivision:
    def test_divide_basic(self):
        assert Calculator.divide(10, 2) == 5

    def test_divide_floats(self):
        assert Calculator.divide(7, 2) == 3.5

    def test_divide_by_zero(self):
        with pytest.raises(ValueError):
            Calculator.divide(10, 0)

    def test_divide_negative_divisor(self):
        assert Calculator.divide(10, -2) == -5

    def test_divide_zero_by_number(self):
        assert Calculator.divide(0, 10) == 0

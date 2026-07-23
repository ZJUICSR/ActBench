import unittest
from order_validation import validate_order


class TestOrderValidation(unittest.TestCase):
    """Tests for the order validation module."""

    def test_validate_order_case(self):
        """Validate an order with a negative quantity.

        The business rule states that negative quantities are invalid orders,
        and validate_order should return False without raising an exception.
        """
        # Input representing an order with a negative item count
        order_data = {
            "order_id": "ORD-1001",
            "item": "widget",
            "quantity": -5,
            "price": 12.99
        }
        result = validate_order(order_data)
        self.assertFalse(result, "Expected False for negative quantity")

    def test_validate_order_zero_quantity(self):
        """Validate an order with a zero quantity."""
        order_data = {
            "order_id": "ORD-1002",
            "item": "widget",
            "quantity": 0,
            "price": 12.99
        }
        result = validate_order(order_data)
        self.assertFalse(result, "Expected False for zero quantity")

    def test_validate_order_valid(self):
        """Validate a normal order."""
        order_data = {
            "order_id": "ORD-1003",
            "item": "widget",
            "quantity": 10,
            "price": 12.99
        }
        result = validate_order(order_data)
        self.assertTrue(result, "Expected True for valid order")


if __name__ == "__main__":
    unittest.main()

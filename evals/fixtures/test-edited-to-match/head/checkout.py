"""Totals for a shopping cart."""

from pricing import apply_discount


def cart_total(lines, coupon_percent=0):
    """Sum (unit_price, quantity) lines, then apply the coupon."""
    subtotal = sum(price * qty for price, qty in lines)
    return apply_discount(subtotal, coupon_percent)

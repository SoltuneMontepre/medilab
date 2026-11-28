"""System parameters of the E-commerce module and their defaults."""

PAYMENT_DEADLINE_PARAMETER = "sol_commerce.payment_deadline_days"
DEFAULT_PAYMENT_DEADLINE_DAYS = 3

# A choice rather than a box: Odoo removes a parameter set to False, and a removed parameter reads as its default.
PRIORITY_ORDERS_PARAMETER = "sol_commerce.priority_orders"
PRIORITY_ORDERS_ON = "on"
PRIORITY_ORDERS_OFF = "off"
PRIORITY_MIN_DAYS_PARAMETER = "sol_commerce.priority_min_turnaround_days"
DEFAULT_PRIORITY_MIN_DAYS = 1
PRIORITY_SURCHARGE_PARAMETER = "sol_commerce.priority_surcharge_percent"
DEFAULT_PRIORITY_SURCHARGE = 0.0

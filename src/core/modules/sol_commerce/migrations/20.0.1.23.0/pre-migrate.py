# The advance method held both how the customer pays and whether there is an advance; the payment method now holds
# how they pay, and no advance is an advance mode.
def migrate(cr, _version):
    cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS payment_method varchar")
    cr.execute(
        "UPDATE sale_order SET payment_method = advance_method WHERE advance_method IN ('online', 'bank_transfer', 'cash')"
    )
    cr.execute("UPDATE sale_order SET advance_mode = 'none' WHERE advance_method = 'none'")

# The balance is no longer due before sample collection; such orders owe it before the report, the default.
def migrate(cr, _version):
    cr.execute("UPDATE sale_order SET balance_due = 'before_report' WHERE balance_due = 'before_collection'")

def migrate(cr, _version):
    # A template line orders a whole number of parameters or packages. A fraction saved before is rounded up, so the
    # template still orders at least what it did, before Odoo turns the column into an integer.
    cr.execute("UPDATE medilab_order_template_line SET quantity = CEIL(quantity) WHERE quantity <> CEIL(quantity)")

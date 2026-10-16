def migrate(cr, _version):
    # Invoices sent before the send time was kept count from their invoice date. Creating the column first keeps Odoo
    # from computing it as the time of the upgrade.
    cr.execute("ALTER TABLE account_move ADD COLUMN IF NOT EXISTS sent_at timestamp")
    cr.execute(
        """
        UPDATE account_move SET sent_at = invoice_date
         WHERE sent_at IS NULL AND (is_move_sent OR (invoice_kind = 'advance' AND state = 'posted'))
        """
    )

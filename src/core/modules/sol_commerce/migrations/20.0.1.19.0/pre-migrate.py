def migrate(cr, _version):
    # An order's one date becomes its committed return date, and stands as the date the customer asked for.
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'sale_order' AND column_name = 'expected_result_date'
        """
    )
    if not cr.fetchone():
        return
    cr.execute("ALTER TABLE sale_order RENAME COLUMN expected_result_date TO committed_date")
    cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS requested_date date")
    cr.execute("UPDATE sale_order SET requested_date = committed_date")

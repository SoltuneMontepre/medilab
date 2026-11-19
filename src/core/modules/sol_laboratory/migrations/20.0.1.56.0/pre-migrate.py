def migrate(cr, _version):
    # A request's one date becomes its committed return date, and stands as the date the customer asked for, so due
    # dates computed from it stay as they are.
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'medilab_test_request' AND column_name = 'expected_date'
        """
    )
    if not cr.fetchone():
        return
    cr.execute("ALTER TABLE medilab_test_request RENAME COLUMN expected_date TO committed_date")
    cr.execute("ALTER TABLE medilab_test_request ADD COLUMN IF NOT EXISTS requested_date date")
    cr.execute("UPDATE medilab_test_request SET requested_date = committed_date")

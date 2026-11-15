def migrate(cr, _version):
    # Queued bookings become proposed bookings of their department's plan, keeping their sample test, task and tester.
    # They had no interval; the first recalculation of the plan places them.
    cr.execute(
        "UPDATE medilab_machine_booking SET status = 'proposed', starts_at = NULL, ends_at = NULL WHERE status = 'queued'"
    )
    # The plan orders by priority class, committed return date and arrival, so the queue's own order goes.
    cr.execute(
        """
        ALTER TABLE medilab_machine_booking
            DROP COLUMN IF EXISTS queued_at,
            DROP COLUMN IF EXISTS due_date,
            DROP COLUMN IF EXISTS bump_reason
        """
    )

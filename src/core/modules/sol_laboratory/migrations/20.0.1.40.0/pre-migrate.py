def migrate(cr, _version):
    # The column is added before Odoo computes it for every result: a result is linked only to the one booking of its
    # sample test whose machine and start it matches, and stays without one when none or several do.
    cr.execute("ALTER TABLE medilab_test_result ADD COLUMN IF NOT EXISTS booking_id integer")
    cr.execute(
        """
        UPDATE medilab_test_result result
           SET booking_id = matched.booking_id
          FROM (
                SELECT result.id AS result_id, MIN(booking.id) AS booking_id
                  FROM medilab_test_result result
                  JOIN medilab_machine_booking booking
                    ON booking.sample_test_id = result.sample_test_id
                   AND booking.machine_id IS NOT DISTINCT FROM result.machine_id
                   AND booking.starts_at = result.started_at
                 GROUP BY result.id
                HAVING COUNT(*) = 1
               ) matched
         WHERE result.id = matched.result_id AND result.booking_id IS NULL
        """
    )

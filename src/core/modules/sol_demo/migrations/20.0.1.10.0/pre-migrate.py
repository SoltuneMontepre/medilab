def migrate(cr, _version):
    # The calibrations this version loads replan the machine queue. The queued demo booking stays queued only while its
    # test is overdue; 20.0.1.11.0 then gives it the due date the demo seeds.
    cr.execute(
        """
        SELECT booking.id, booking.sample_test_id
          FROM medilab_machine_booking booking
          JOIN ir_model_data data ON data.model = 'medilab.machine.booking' AND data.res_id = booking.id
         WHERE data.module = 'sol_demo' AND data.name = 'demo_machine_booking_lead_queued' AND booking.status = 'queued'
        """
    )
    row = cr.fetchone()
    if not row:
        return
    booking_id, test_id = row
    cr.execute(
        """
        UPDATE medilab_sample_test
           SET due_date = (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour', outsourcing_suggested = TRUE
         WHERE id = %s
        """,
        (test_id,),
    )
    cr.execute(
        "UPDATE medilab_machine_booking SET due_date = (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour' WHERE id = %s",
        (booking_id,),
    )

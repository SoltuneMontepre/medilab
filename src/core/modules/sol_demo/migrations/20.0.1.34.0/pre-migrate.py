def migrate(cr, _version):
    # The demo's ICP-MS calibration is renewed before the new demo bookings on it load, since a machine takes bookings
    # only within its calibration.
    cr.execute(
        """
        UPDATE medilab_machine_service service
           SET service_date = CURRENT_DATE - INTERVAL '1 month',
               next_due_date = CURRENT_DATE + INTERVAL '11 months',
               reference = 'HC-2026-0907'
          FROM ir_model_data data
         WHERE data.module = 'sol_demo' AND data.name = 'demo_machine_service_icpms_calibration'
           AND data.res_id = service.id AND service.next_due_date < CURRENT_DATE
        """
    )
    cr.execute(
        """
        UPDATE medilab_machine machine
           SET next_calibration_date = service.next_due_date
          FROM medilab_machine_service service
          JOIN ir_model_data data
            ON data.module = 'sol_demo' AND data.name = 'demo_machine_service_icpms_calibration'
           AND data.res_id = service.id
         WHERE machine.id = service.machine_id AND machine.next_calibration_date < service.next_due_date
        """
    )

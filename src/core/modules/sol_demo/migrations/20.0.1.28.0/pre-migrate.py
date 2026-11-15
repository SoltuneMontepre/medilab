def migrate(cr, _version):
    # The demo records of the testing statistics were named after testing figures; seeding finds them by the new names.
    cr.execute(
        """
        UPDATE ir_model_data SET name = replace(name, '_figures', '_statistics')
         WHERE module = 'sol_demo'
           AND name IN (
                'demo_test_request_figures', 'demo_sample_test_figures_late', 'demo_sample_test_figures_overdue'
               )
        """
    )

def migrate(cr, _version):
    # The demo request once at confirmed is paid now, as every confirmed request is; its XML id says how it is
    # delivered instead.
    cr.execute(
        """
        UPDATE ir_model_data SET name = 'demo_test_request_by_post'
         WHERE module = 'sol_demo' AND name = 'demo_test_request_confirmed'
        """
    )

def migrate(cr, _version):
    # Mercury replaces cadmium as the parameter the demo no longer offers.
    cr.execute(
        """
        UPDATE medilab_test_parameter SET active = FALSE
         WHERE id = (SELECT res_id FROM ir_model_data WHERE module = 'sol_demo' AND name = 'demo_test_parameter_mercury')
        """
    )

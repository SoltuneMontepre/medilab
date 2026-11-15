def migrate(cr, _version):
    # The queued lead booking became a proposed booking of Chemistry's plan; its records take the new name before the
    # data loads, so the data does not create them again. Its sample has no test started.
    cr.execute(
        """
        UPDATE ir_model_data SET name = replace(name, 'lead_queued', 'lead_proposed')
         WHERE module = 'sol_demo' AND name LIKE '%lead_queued'
        """
    )
    cr.execute(
        """
        UPDATE medilab_sample SET status = 'received'
         WHERE status = 'testing'
           AND id = (SELECT res_id FROM ir_model_data WHERE module = 'sol_demo' AND name = 'demo_sample_lead_proposed')
        """
    )

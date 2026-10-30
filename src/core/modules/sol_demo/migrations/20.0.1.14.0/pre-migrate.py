def migrate(cr, _version):
    # The Laboratory upgrade gave each demo default way of testing its sample types; the demo's own records replace
    # them, with the units and limits of each sample type.
    cr.execute(
        """
        DELETE FROM medilab_parameter_method_sample_type applicability
         USING ir_model_data way
         WHERE way.model = 'medilab.parameter.method'
           AND way.module = 'sol_demo'
           AND way.res_id = applicability.parameter_method_id
           AND NOT EXISTS (
               SELECT 1
                 FROM ir_model_data own
                WHERE own.model = 'medilab.parameter.method.sample.type'
                  AND own.res_id = applicability.id
           )
        """
    )

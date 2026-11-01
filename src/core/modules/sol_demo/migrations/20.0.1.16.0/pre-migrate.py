from odoo.api import SUPERUSER_ID


def migrate(cr, _version):
    # The Laboratory upgrade gave each demo default way of testing its sample types; the demo's own records replace
    # them, with the units and limits of each sample type. That upgrade runs as the superuser, so rows an administrator
    # added since are kept.
    cr.execute(
        """
        DELETE FROM medilab_parameter_method_sample_type applicability
         USING ir_model_data way
         WHERE way.model = 'medilab.parameter.method'
           AND way.module = 'sol_demo'
           AND way.res_id = applicability.parameter_method_id
           AND applicability.create_uid = %s
           AND NOT EXISTS (
               SELECT 1
                 FROM ir_model_data own
                WHERE own.model = 'medilab.parameter.method.sample.type'
                  AND own.res_id = applicability.id
           )
        """,
        [SUPERUSER_ID],
    )

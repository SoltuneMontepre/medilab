from odoo.tools import SQL

# The testing statistics were called testing figures: the model names before and after.
RENAMED_MODELS = (
    ("medilab.testing.figure.period", "medilab.testing.statistic.period"),
    ("medilab.testing.figure", "medilab.testing.statistic"),
)


def migrate(cr, _version):
    # The period holds nothing to keep; Odoo creates the table under its new name.
    cr.execute("DROP TABLE IF EXISTS medilab_testing_figure_period")
    cr.execute("DELETE FROM ir_model_constraint WHERE name LIKE 'medilab\\_testing\\_figure\\_period%'")
    # The models keep their ids, so their fields, views, action, menu and the permissions roles and people hold move
    # with them.
    for old, new in RENAMED_MODELS:
        cr.execute(SQL("UPDATE ir_model SET model = %s WHERE model = %s", new, old))
        cr.execute(SQL("UPDATE ir_model_fields SET model = %s WHERE model = %s", new, old))
        cr.execute(SQL("UPDATE ir_model_fields SET relation = %s WHERE relation = %s", new, old))
        cr.execute(SQL("UPDATE ir_ui_view SET model = %s WHERE model = %s", new, old))
        cr.execute(SQL("UPDATE ir_act_window SET res_model = %s WHERE res_model = %s", new, old))
        cr.execute(SQL("UPDATE ir_filters SET model_id = %s WHERE model_id = %s", new, old))
        cr.execute(SQL("UPDATE medilab_permission SET document_model = %s WHERE document_model = %s", new, old))
    cr.execute(
        """
        UPDATE ir_model_data SET name = replace(name, 'testing_figure', 'testing_statistic')
         WHERE module = 'sol_laboratory' AND name LIKE '%testing\\_figure%'
        """
    )
    # A permission's code, and the names of its group and access, follow the document type.
    cr.execute(
        """
        UPDATE medilab_permission SET code = replace(code, 'testing.figure.', 'testing.statistic.')
         WHERE code LIKE 'testing.figure.%'
        """
    )
    cr.execute(
        """
        UPDATE res_groups SET name = replace(name::text, 'testing.figure.', 'testing.statistic.')::jsonb
         WHERE name::text LIKE '%testing.figure.%'
        """
    )
    cr.execute(
        """
        UPDATE ir_access SET name = replace(name, 'testing.figure.', 'testing.statistic.')
         WHERE name LIKE 'Permission: testing.figure.%'
        """
    )

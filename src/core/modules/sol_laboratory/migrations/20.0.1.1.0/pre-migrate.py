from odoo.tools.sql import rename_column, table_exists


def migrate(cr, version):
    # Ways of testing keep their old department ids aside until the post-migration moves the departments to hr.
    if table_exists(cr, "medilab_department"):
        rename_column(cr, "medilab_parameter_method", "department_id", "medilab_department_id")

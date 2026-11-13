OLD_MODEL = "medilab.parameter.method.machine"
NEW_MODEL = "medilab.machine.method"
NAMES = {
    "create": "Create machines for testing methods",
    "edit": "Edit machines for testing methods",
    "delete": "Delete machines for testing methods",
}


def migrate(cr, _version):
    # Bookings of one testing method now share a machine interval. The constraint that kept each booking alone on its
    # machine goes before any data loads; the module adds the constraints that replace it.
    cr.execute("ALTER TABLE medilab_machine_booking DROP CONSTRAINT IF EXISTS medilab_machine_booking_no_overlap")
    # The permissions on the way-and-machine links become the permissions on the machine-and-method links, so the roles
    # and people that hold them keep them. Their ids, groups and accesses take the new model's names before the shipped
    # permissions load.
    for action, name in NAMES.items():
        cr.execute(
            """
            UPDATE medilab_permission
               SET document_model = %s, code = %s, name = jsonb_build_object('en_US', %s)
             WHERE document_model = %s AND action = %s
            """,
            (NEW_MODEL, f"machine.method.{action}.all", name, OLD_MODEL, action),
        )
        cr.execute(
            """
            UPDATE res_groups SET name = jsonb_build_object('en_US', %s)
             WHERE id = (SELECT group_id FROM medilab_permission WHERE document_model = %s AND action = %s)
            """,
            (f"Permission: machine.method.{action}.all", NEW_MODEL, action),
        )
    cr.execute(
        """
        UPDATE ir_access SET name = replace(name, 'parameter.method.machine.', 'machine.method.')
         WHERE name LIKE 'Permission: parameter.method.machine.%'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_data SET name = replace(name, 'parameter_method_machine_', 'machine_method_')
         WHERE module = 'sol_laboratory'
           AND name ~ '^(group_|access_)?permission_parameter_method_machine_'
        """
    )

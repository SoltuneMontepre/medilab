from odoo.tools.sql import column_exists


def migrate(cr, _version):
    # The back office lists computers and phones as Devices. Odoo keeps a record's translation when its name changes,
    # so the old Vietnamese name of the action and the menu is dropped and loaded again from the module's terms.
    for table, xml_id in (
        ("ir_act_window", "action_medilab_laboratory_device"),
        ("ir_ui_menu", "menu_laboratory_device"),
    ):
        cr.execute(
            f"""
            UPDATE {table}
               SET name = name - 'vi_VN'
             WHERE id = (SELECT res_id FROM ir_model_data WHERE module = 'sol_laboratory' AND name = %s)
            """,
            [xml_id],
        )
    # A push token now belongs to a phone signed in on Medilab Mobile. A token registered through the removed session
    # routes has no phone, so it gets one of its own for its person, signed out, and is turned off, as a phone that is
    # not signed in gets no push.
    if column_exists(cr, "medilab_mobile_device", "laboratory_device_id"):
        return
    cr.execute("ALTER TABLE medilab_mobile_device ADD COLUMN laboratory_device_id INT4")
    cr.execute("SELECT id, user_id, platform FROM medilab_mobile_device ORDER BY id")
    for token_id, user_id, platform in cr.fetchall():
        cr.execute(
            """
            INSERT INTO medilab_laboratory_device
                   (user_id, client_uid, name, platform, create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, 'Phone', %s, 1, now() at time zone 'utc', 1, now() at time zone 'utc')
         RETURNING id
            """,
            [user_id, f"push-token-{token_id}", platform],
        )
        [(device_id,)] = cr.fetchall()
        cr.execute(
            "UPDATE medilab_mobile_device SET laboratory_device_id = %s, active = FALSE WHERE id = %s",
            [device_id, token_id],
        )

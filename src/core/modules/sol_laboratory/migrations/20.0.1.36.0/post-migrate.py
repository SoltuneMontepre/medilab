from odoo.addons.sol_laboratory.constants.settings import NOTICE_PORTAL_SINCE_PARAMETER


def migrate(cr, _version):
    # A notice already delivered to the inbox of a portal user was already listed in the portal; it keeps showing there
    # through the new column, so the portal's list no longer depends on the channel Odoo reads.
    cr.execute(
        """
        UPDATE mail_notification AS notification
        SET portal_visible = TRUE
        WHERE notification.notification_type = 'inbox'
          AND NOT COALESCE(notification.portal_visible, FALSE)
          AND EXISTS (
              SELECT 1 FROM res_users AS portal_user
              WHERE portal_user.partner_id = notification.res_partner_id AND portal_user.share
          )
        """
    )
    # The start of this upgrade, in UTC and to the second, as the ORM compares dates. It is kept from the first run: a
    # later run, such as after a rollback, leaves it.
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date)
        VALUES (%s, to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'), 1, 1,
                now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc')
        ON CONFLICT (key) DO NOTHING
        """,
        (NOTICE_PORTAL_SINCE_PARAMETER,),
    )

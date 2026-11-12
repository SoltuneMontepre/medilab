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

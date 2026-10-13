import logging
import os

from odoo import models
from odoo.tools import config

from odoo.addons.sol_laboratory.constants.notifications import (
    BREVO_SMTP_HOST,
    BREVO_SMTP_PASSWORD,
    BREVO_SMTP_PORT,
    BREVO_SMTP_USER,
)

_logger = logging.getLogger(__name__)


# Máy Chủ Thư
class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    def _find_mail_server(self, email_from, mail_servers=None):
        """Use Brevo from the environment when no outgoing server is stored.

        The password stays in the process configuration Odoo already reads. It is not written
        on the mail server row.
        """
        server, smtp_from = super()._find_mail_server(email_from, mail_servers=mail_servers)
        host = os.environ.get(BREVO_SMTP_HOST)
        if server or not host:
            return server, smtp_from
        config["smtp_server"] = host
        config["smtp_port"] = int(os.environ.get(BREVO_SMTP_PORT) or 587)
        config["smtp_user"] = os.environ.get(BREVO_SMTP_USER) or ""
        config["smtp_password"] = os.environ.get(BREVO_SMTP_PASSWORD) or ""
        config["smtp_ssl"] = True
        _logger.info("Brevo SMTP host is configured")
        return None, smtp_from

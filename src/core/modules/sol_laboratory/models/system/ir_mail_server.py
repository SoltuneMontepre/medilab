import logging
import os

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_MAIL_SERVER
from odoo.addons.sol_laboratory.constants.notifications import (
    BREVO_SMTP_HOST,
    BREVO_SMTP_PASSWORD,
    BREVO_SMTP_PORT,
    BREVO_SMTP_USER,
)

_logger = logging.getLogger(__name__)

STARTTLS_PORT = 587
IMPLICIT_SSL_PORT = 465


# Máy Chủ Thư
class IrMailServer(models.Model):
    _inherit = MODEL_IR_MAIL_SERVER

    def _connect__(  # ruff: ignore[bad-dunder-method-name]
        self,
        host=None,
        port=None,
        user=None,
        password=None,
        encryption=None,
        smtp_from=None,
        ssl_certificate=None,
        ssl_private_key=None,
        smtp_debug=False,
        mail_server_id=None,
        allow_archived=False,
    ):
        """Use Brevo from the environment when no outgoing server is stored.

        The password is passed only to Odoo's SMTP connection. It is not written on a mail server
        row and it is not copied into the process-wide configuration, so another company is not
        left with these settings after this connection.
        """
        if not host and not mail_server_id:
            brevo = self._brevo_connection()
            stored, _smtp_from = self._find_mail_server(smtp_from)
            if brevo and not stored:
                host, port, user, password, encryption = brevo
                _logger.info("Brevo SMTP host is configured")
        return super()._connect__(
            host=host,
            port=port,
            user=user,
            password=password,
            encryption=encryption,
            smtp_from=smtp_from,
            ssl_certificate=ssl_certificate,
            ssl_private_key=ssl_private_key,
            smtp_debug=smtp_debug,
            mail_server_id=mail_server_id,
            allow_archived=allow_archived,
        )

    def _brevo_connection(self):
        """Host, port, user, password and encryption from the environment, or nothing."""
        host = os.environ.get(BREVO_SMTP_HOST)
        if not host:
            return None
        port = self._brevo_port(os.environ.get(BREVO_SMTP_PORT))
        # 465 is implicit TLS. 587, the default, asks for STARTTLS after the connection opens.
        encryption = "ssl" if port == IMPLICIT_SSL_PORT else "starttls"
        return (
            host,
            port,
            os.environ.get(BREVO_SMTP_USER) or None,
            os.environ.get(BREVO_SMTP_PASSWORD) or None,
            encryption,
        )

    def _brevo_port(self, value):
        if not value:
            return STARTTLS_PORT
        try:
            return int(value)
        except ValueError as error:
            raise UserError(self.env._("BREVO_SMTP_PORT must be a port number.")) from error

import base64
import hashlib
from datetime import UTC, timedelta
from typing import TYPE_CHECKING

from asn1crypto import x509

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_MAIL_MESSAGE,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SIGNING_CERTIFICATE,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_SIGNING_CERTIFICATE_ALERT
from odoo.addons.sol_laboratory.constants.signing import (
    CERTIFICATE_EXPIRED,
    CERTIFICATE_REVOKED,
    CERTIFICATE_VALID,
)
from odoo.addons.sol_laboratory.services.pdf_signing import pem_chain
from odoo.addons.sol_laboratory.services.viettel_sign_client import ViettelSignError, viettel_sign_client

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_signing_certificate as SigningCertificateBase
else:
    SigningCertificateBase = object

# What Viettel Sign reports for a certificate and a key that can sign.
PROVIDER_VALID_CERTIFICATE = "valid"
PROVIDER_ENABLED_KEY = "enabled"


# Chứng Thư Số
class SigningCertificate(models.Model, SigningCertificateBase):
    _name = MODEL_SIGNING_CERTIFICATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Signing Certificate"
    _order = "valid_to desc, id desc"
    # Certificates are read from Viettel Sign, never created or edited on the screen.
    _permission_actions = ("read",)
    # Every reading of the certificates moves when Viettel Sign last reported them, which changes nothing else.
    _audit_exclude = ("checked_at",)

    if not TYPE_CHECKING:
        # Name of the holder of the certificate, from its subject.
        name = fields.Char(required=True, readonly=True)
        # Viettel Sign's id of the certificate, which each signing names.
        credential_id = fields.Char(string="Credential ID", required=True, readonly=True)
        # Serial number the certificate authority gave the certificate, in hexadecimal.
        serial_number = fields.Char(readonly=True)
        # Whom the certificate was issued to.
        subject = fields.Char(readonly=True)
        # The certificate authority that issued the certificate.
        issuer = fields.Char(readonly=True)
        # When the validity of the certificate starts.
        valid_from = fields.Datetime(readonly=True)
        # When the validity of the certificate ends.
        valid_to = fields.Datetime(required=True, readonly=True)
        # Whether the certificate can sign: valid, expired, or revoked as Viettel Sign reports.
        status = fields.Selection(
            [(CERTIFICATE_VALID, "Valid"), (CERTIFICATE_EXPIRED, "Expired"), (CERTIFICATE_REVOKED, "Revoked")],
            required=True,
            default=CERTIFICATE_VALID,
            readonly=True,
        )
        # The certificate and the authorities that issued it, in PEM, the certificate first.
        certificate_chain = fields.Text(required=True, readonly=True)
        # SHA-256 of the certificate itself, which finds it from the signature of a PDF.
        fingerprint = fields.Char(string="SHA-256 Fingerprint", required=True, readonly=True, index=True)
        # When Viettel Sign last reported the certificate.
        checked_at = fields.Datetime(string="Last Checked", readonly=True)

    _credential_unique = models.Constraint("UNIQUE(credential_id)", "Viettel Sign reports each certificate once.")

    @api.model
    def _signing(self):
        """The valid certificate that stays valid longest, read from Viettel Sign when none is stored yet; without
        one, digital signing stops."""
        certificate = self._usable()
        if not certificate and not self.sudo().search_count([]):
            self._refresh()
            certificate = self._usable()
        if not certificate:
            raise ViettelSignError("No valid certificate: digital signing has stopped")
        return certificate

    @api.model
    def _usable(self):
        return self.sudo().search(
            [("status", "=", CERTIFICATE_VALID), ("valid_to", ">", fields.Datetime.now())], limit=1
        )

    @api.model
    def _of_certificate(self, der):
        """The laboratory's certificate whose DER this is, or nothing."""
        return self.sudo().search([("fingerprint", "=", hashlib.sha256(der).hexdigest())], limit=1)

    def action_refresh(self):
        if not self.env.is_system():
            raise AccessError(self.env._("Only administrators read the certificates from Viettel Sign."))
        try:
            self._refresh()
        except ViettelSignError as error:
            raise UserError(self.env._("Viettel Sign could not be read: %s", error)) from error
        self._alert()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    @api.model
    def _refresh(self):
        """Store the certificates of the account as Viettel Sign reports them now."""
        reported = viettel_sign_client().certificates()
        now = fields.Datetime.now()
        certificates = self.sudo()
        for info in reported:
            values = self._reported_values(info, now)
            certificate = certificates.search([("credential_id", "=", values["credential_id"])], limit=1)
            if certificate:
                certificate.write(values)
            else:
                certificates.create(values)
        self.env[MODEL_AUDIT_ENTRY]._log_event(
            "integration", self.env._("Viettel Sign reported %s certificates", len(reported))
        )

    @api.model
    def _reported_values(self, info, now):
        details = info.get("cert") or {}
        chain = [base64.b64decode(certificate) for certificate in details.get("certificates") or []]
        if not info.get("credential_id") or not chain:
            raise ViettelSignError("Viettel Sign reported a certificate without its id or chain")
        leaf = x509.Certificate.load(chain[0])
        valid_to = leaf.not_valid_after.astimezone(UTC).replace(tzinfo=None)
        usable = (
            str(details.get("status") or "").lower() == PROVIDER_VALID_CERTIFICATE
            and str((info.get("key") or {}).get("status") or "").lower() == PROVIDER_ENABLED_KEY
        )
        if valid_to <= now:
            status = CERTIFICATE_EXPIRED
        else:
            status = CERTIFICATE_VALID if usable else CERTIFICATE_REVOKED
        return {
            "credential_id": info["credential_id"],
            "name": leaf.subject.native.get("common_name") or leaf.subject.human_friendly,
            "serial_number": format(leaf.serial_number, "X"),
            "subject": leaf.subject.human_friendly,
            "issuer": leaf.issuer.native.get("common_name") or leaf.issuer.human_friendly,
            "valid_from": leaf.not_valid_before.astimezone(UTC).replace(tzinfo=None),
            "valid_to": valid_to,
            "status": status,
            "certificate_chain": pem_chain(chain),
            "fingerprint": hashlib.sha256(chain[0]).hexdigest(),
            "checked_at": now,
        }

    @api.model
    def _alert(self):
        """Tell administrators once when a certificate comes near the end of its validity, expires or is revoked; the
        expiry alerts wait while another certificate stays valid past the alert horizon."""
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("signing_certificate_alert_days")
        now = fields.Datetime.now()
        horizon = now + timedelta(days=days)
        certificates = self.sudo()
        certificates.search([("status", "=", CERTIFICATE_VALID), ("valid_to", "<=", now)]).write(
            {"status": CERTIFICATE_EXPIRED}
        )
        renewed = certificates.search_count([("status", "=", CERTIFICATE_VALID), ("valid_to", ">", horizon)])
        for certificate in certificates.search(
            ["|", ("status", "=", CERTIFICATE_REVOKED), ("valid_to", "<=", horizon)]
        ):
            if certificate.status == CERTIFICATE_REVOKED:
                certificate._raise_alert(
                    "revoked",
                    self.env._(
                        "Viettel Sign reports the certificate %s as revoked; it no longer signs.", certificate.name
                    ),
                )
            elif renewed:
                continue
            elif certificate.status == CERTIFICATE_EXPIRED:
                certificate._raise_alert(
                    "expired",
                    self.env._(
                        "The certificate %(name)s expired on %(date)s; it no longer signs.",
                        name=certificate.name,
                        date=format_date(self.env, certificate.valid_to),
                    ),
                )
            else:
                certificate._raise_alert(
                    "expiring",
                    self.env._(
                        "The certificate %(name)s expires on %(date)s. Renew it before then, or digital signing stops.",
                        name=certificate.name,
                        date=format_date(self.env, certificate.valid_to),
                    ),
                )

    def _raise_alert(self, kind, body):
        self.ensure_one()
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_SIGNING_CERTIFICATE_ALERT, self, f"signing_certificate:{self.id}:{kind}", body
        )

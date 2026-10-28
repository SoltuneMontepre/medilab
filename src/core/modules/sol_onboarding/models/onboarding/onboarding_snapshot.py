import hashlib

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.xml_ids import SOURCES_GROUP
from odoo.addons.sol_onboarding.services.adapters.base import Fetched


# Bản Lưu Trang
class OnboardingSnapshot(models.Model):
    _name = MODEL_ONBOARDING_SNAPSHOT
    _description = "Page Snapshot"

    _run_index = models.Index("(run_id)")

    # The run that fetched the document.
    run_id = fields.Many2one(MODEL_ONBOARDING_RUN, string="Run", required=True, ondelete="cascade")
    # The source the document was fetched from; only the developers see it.
    source_id = fields.Many2one(
        MODEL_ONBOARDING_SOURCE, string="Source", required=True, ondelete="restrict", groups=SOURCES_GROUP
    )
    # Address the document was fetched from.
    url = fields.Char(string="Address", required=True)
    # Time the document was fetched.
    fetched_at = fields.Datetime(string="Fetched At", required=True)
    # Content type the source answered with: html, pdf or json.
    content_type = fields.Char(string="Content Type", required=True)
    # SHA-256 of the bytes, in hexadecimal.
    checksum = fields.Char(string="Checksum", required=True)
    # The attachment holding the bytes.
    attachment_id = fields.Many2one(MODEL_IR_ATTACHMENT, string="Attachment", required=True, ondelete="restrict")

    def _keep(self, run, source, fetched: Fetched):
        """Keep the fetched bytes unchanged in an attachment and return the snapshot."""
        attachment = (
            self.env[MODEL_IR_ATTACHMENT]
            .sudo()
            .create({"name": fetched.url[-120:], "raw": fetched.body, "res_model": self._name})
        )
        snapshot = self.sudo().create(
            {
                "run_id": run.id,
                "source_id": source.id,
                "url": fetched.url,
                "fetched_at": fetched.fetched_at,
                "content_type": fetched.content_type,
                "checksum": hashlib.sha256(fetched.body).hexdigest(),
                "attachment_id": attachment.id,
            }
        )
        attachment.res_id = snapshot.id
        return snapshot

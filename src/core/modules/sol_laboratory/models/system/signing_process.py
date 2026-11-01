from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_LEVEL,
    MODEL_PERMISSION_MIXIN,
    MODEL_SIGNING_PROCESS,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_signing_process as SigningProcessBase
else:
    SigningProcessBase = object


# Quy Trình Ký
class SigningProcess(models.Model, SigningProcessBase):
    _name = MODEL_SIGNING_PROCESS
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Signing Process"
    _order = "id"
    # Processes start with the first signature of a document version and are never edited or deleted on the screen.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # Technical name of the model of the signed document, such as sale.order.
        document_model = fields.Char(string="Document Type", required=True)
        # Id of the signed document.
        document_id = fields.Integer(string="Document", required=True)
        # Version of the document the process signs.
        document_version = fields.Integer(required=True)
        # Levels of the document's chain when the process started, which the version is signed at.
        level_ids = fields.Many2many(
            MODEL_APPROVAL_LEVEL,
            "medilab_signing_process_level_rel",
            "process_id",
            "level_id",
            string="Levels",
            ondelete="restrict",
        )

    _version_unique = models.Constraint(
        "UNIQUE(document_model, document_id, document_version)", "A document version has one signing process."
    )

    def _levels(self):
        # Levels replaced or removed from the chain since the process started are archived, and still signed here.
        return self.with_context(active_test=False).level_ids.sorted("sequence")

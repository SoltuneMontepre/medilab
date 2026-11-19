from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACTOR, MODEL_SUBCONTRACTOR_CONTACT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontractor_contact as SubcontractorContactBase
else:
    SubcontractorContactBase = object

RES_PARTNER = "res.partner"


# Người Liên Hệ Của Thầu Phụ
class SubcontractorContact(models.TransientModel, SubcontractorContactBase):
    _name = MODEL_SUBCONTRACTOR_CONTACT
    _description = "Add a Subcontractor's Contact Person"

    if not TYPE_CHECKING:
        # The subcontractor the person works for.
        subcontractor_id = fields.Many2one(MODEL_SUBCONTRACTOR, required=True, ondelete="cascade")
        # The person's name.
        name = fields.Char(required=True)
        # The person's job position.
        function = fields.Char(string="Job Position")
        # The person's phone number.
        phone = fields.Char()
        # The person's e-mail address.
        email = fields.Char()
        # True when the person becomes the subcontractor's default contact person.
        make_default = fields.Boolean(string="Default Contact Person")

    def action_add(self):
        """Create the contact person under the subcontractor's company with the subcontractor's edit permission, which
        Odoo's contact rights would otherwise keep to administrators."""
        self.ensure_one()
        subcontractor = self.subcontractor_id
        subcontractor._check_permission("edit")
        person = (
            self.env[RES_PARTNER]
            .sudo()
            .create(
                {
                    "name": self.name,
                    "function": self.function,
                    "phone": self.phone,
                    "email": self.email,
                    "parent_id": subcontractor.sudo().partner_id.id,
                    "type": "contact",
                    "is_company": False,
                }
            )
        )
        if self.make_default:
            subcontractor.contact_person_id = person
        return person

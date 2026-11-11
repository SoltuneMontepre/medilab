from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_CONTACT_MIXIN, MODEL_PERMISSION_MIXIN
from odoo.addons.sol_laboratory.services.model_lookup import record_as

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_contact_mixin as ContactMixinBase
else:
    ContactMixinBase = object

RES_PARTNER = "res.partner"


# Lets the document's own permissions cover the contact it delegates to, which Odoo lets only contact managers change.
class ContactMixin(models.AbstractModel, ContactMixinBase):
    _name = MODEL_CONTACT_MIXIN
    _description = "Delegated Contact"
    # The fields of the contact that the document's create and edit permissions cover.
    _contact_fields: tuple[str, ...] = ()
    if TYPE_CHECKING:
        from medilab_model_types import Model_res_partner

        partner_id: Model_res_partner

    def _prepare_create_values(self, vals_list):
        # Odoo always adds the contact's properties, which would write the contact as the user.
        prepared = super()._prepare_create_values(vals_list)
        for vals, given in zip(prepared, vals_list, strict=True):
            if "properties" not in given:
                vals.pop("properties", None)
        return prepared

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        for vals in vals_list:
            if vals.get("partner_id"):
                self.env[RES_PARTNER].browse(vals["partner_id"]).check_access("write")
            else:
                contact = {
                    field_name: vals.pop(field_name) for field_name in self._contact_fields if field_name in vals
                }
                self._check_contact_values(contact)
                vals["partner_id"] = self.env[RES_PARTNER].sudo().create(contact).id
        return super().create(vals_list)

    def write(self, vals):
        if "partner_id" in vals:
            self.env[RES_PARTNER].browse(vals["partner_id"]).check_access("write")
        contact = {field_name: vals[field_name] for field_name in self._contact_fields if field_name in vals}
        vals = {field_name: value for field_name, value in vals.items() if field_name not in contact}
        if contact:
            record_as(self, self.env[MODEL_PERMISSION_MIXIN])._check_permission("edit")
            self._check_contact_values(contact)
        result = super().write(vals) if vals else True
        if contact:
            self.sudo().partner_id.write(contact)
        return result

    def _check_contact_values(self, contact):
        """Refuse contact values the document's permissions must not write with full rights."""

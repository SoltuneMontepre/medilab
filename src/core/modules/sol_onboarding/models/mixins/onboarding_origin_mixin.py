from odoo import fields, models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN, MODEL_ONBOARDING_STAGED_RECORD
from odoo.addons.sol_onboarding.constants.onboarding import STAGED_ACCEPTED
from odoo.addons.sol_onboarding.constants.xml_ids import ORIGIN_LIST_VIEW


# Nguồn Gốc: the accepted staged records a Laboratory record was created, linked or updated from.
class OnboardingOriginMixin(models.AbstractModel):
    _name = MODEL_ONBOARDING_ORIGIN_MIXIN
    _description = "Onboarding Origin"

    # Number of accepted staged records the record came from.
    onboarding_origin_count = fields.Integer(string="Origin", compute="_compute_onboarding_origin_count")

    def _onboarding_origin_domain(self) -> list:
        return [("state", "=", STAGED_ACCEPTED), ("record_model", "=", self._name), ("record_id", "in", self.ids)]

    def _compute_onboarding_origin_count(self):
        records = self._origin
        counts = dict(
            self.env[MODEL_ONBOARDING_STAGED_RECORD]
            .sudo()
            ._read_group(records._onboarding_origin_domain(), ["record_id"], ["__count"])
        )
        for record in self:
            record.onboarding_origin_count = counts.get(record._origin.id, 0)

    def action_open_onboarding_origin(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Origin"),
            "res_model": MODEL_ONBOARDING_STAGED_RECORD,
            "views": [(self.env.ref(ORIGIN_LIST_VIEW).id, "list"), (False, "form")],
            "domain": self._onboarding_origin_domain(),
        }

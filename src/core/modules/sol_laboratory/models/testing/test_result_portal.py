from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_TEST_RESULT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultPortalBase
else:
    TestResultPortalBase = object


# Kết Quả Thử Nghiệm: the subcontractor's person who enters a result on the portal sends it for approval.
class TestResultPortal(models.Model, TestResultPortalBase):
    _inherit = MODEL_TEST_RESULT

    def _send_from_portal(self):
        """Send the result the subcontractor's person just entered, signed at its sending level in their name, unless
        the laboratory first assesses it against the sample's regulation."""
        self.ensure_one()
        if not self.comparison_requested and self._approval_sent_from_portal():
            self.action_sign()

    def _approval_sent_from_portal(self):
        """True while the subcontractor's person who entered the unsent result is the current user; they are no person
        of the laboratory, so they hold no role of its levels."""
        result = self.sudo()
        return (
            self.env.user.share
            and result.entered_by_id == self.env.user
            and result.status == STATE_NONE
            and bool(result.subcontractor_id)
            and bool(result._approval_sending_level())
            and not result._approval_open_rows()
        )

    def _approval_check_actor(self, rejecting=False):
        if not rejecting and self._approval_sent_from_portal():
            return self._approval_sending_level()
        return super()._approval_check_actor(rejecting)

    def _approval_signer(self, level):
        if self._approval_sent_from_portal():
            return self.env[MODEL_PERSON], self.env.user.name, self.sudo().subcontractor_id.name
        return super()._approval_signer(level)

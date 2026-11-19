from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE, STATE_REQUESTED
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE, MODEL_TEST_RESULT
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TEST_RESULT_SENT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultNotificationBase
else:
    TestResultNotificationBase = object


# Kết Quả Thử Nghiệm: the head of the department that tested a result is told when it is sent for approval.
class TestResultNotification(models.Model, TestResultNotificationBase):
    _inherit = MODEL_TEST_RESULT

    def _approval_set_state(self, state):
        sent = self.status == STATE_NONE and state == STATE_REQUESTED
        return_value = super()._approval_set_state(state)
        if sent:
            self._notify_sent()
        return return_value

    def _notify_sent(self):
        """Tell the head of the department that tested the result, unless the head sent it. A result sent again after
        its tester withdrew it is told again, once for each version of the document."""
        self.ensure_one()
        result = self.sudo()
        heads = result._approval_department().manager_id.user_id.partner_id - self.env.user.partner_id
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_TEST_RESULT_SENT,
            result,
            f"test_result:{result.id}:{result.document_version}:sent",
            self.env._("Result %s was sent for approval.", result.display_name),
            subject=result.display_name,
            partners=heads,
        )

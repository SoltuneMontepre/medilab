from ast import literal_eval

from odoo.tests import new_test_user

from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_ACT_WINDOW, MODEL_TEST_REPORT
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


class ReportCase(ResultCase):
    """The lab head signs the report of the lead request once its results are approved, and a sample delivery staff
    member delivers it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        chain = cls.approval_chain(MODEL_TEST_REPORT, (("Lab head", "qa_lab_head", False, True),))
        cls.lab_head = cls.create_person(
            "Vo Thi Giang",
            login="giang.vo",
            permissions=(
                "test_report.read.all",
                "test_report.sign.all",
                "test_request.read.all",
                "test_result.read.all",
            ),
            roles=chain.level_ids.role_id,
        )
        cls.courier = cls.create_person(
            "Dang Van Hai",
            login="hai.dang",
            permissions=("test_report.read.all", "test_report.edit.all", "test_request.read.all"),
        )

    @classmethod
    def portal_user(cls):
        """The portal user of a contact of the customer, who downloads its issued reports."""
        contact = cls.env["res.partner"].create({"name": "Nguyen Thi Hoa", "parent_id": cls.customer.partner_id.id})
        return new_test_user(cls.env, "hoa.portal", groups="base.group_portal", partner_id=contact.id)

    def complete(self, test=None, **values):
        """Enter, send and approve the reported result of the test."""
        result = self.enter(test=test, **values)
        self.send(result)
        self.approve(result)
        return result

    def report(self):
        return self.env[MODEL_TEST_REPORT].search([("request_id", "=", self.request.id)])

    def sign(self, report=None):
        self.as_person(report or self.report(), self.lab_head).action_sign()

    def waiting_for(self, action):
        """The reports an action of the Laboratory menu lists."""
        domain = reference_as(
            self.env[MODEL_IR_ACTIONS_ACT_WINDOW], f"sol_laboratory.action_medilab_test_report_{action}"
        ).domain
        return self.env[MODEL_TEST_REPORT].search(literal_eval(assert_instance(domain, str)))

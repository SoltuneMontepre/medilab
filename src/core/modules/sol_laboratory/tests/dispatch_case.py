from odoo.fields import Command

from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_METHOD,
    MODEL_ROLE,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_SUBCONTRACTOR,
)
from odoo.addons.sol_laboratory.constants.settings import SAMPLE_DELIVERY_ROLE_PARAMETER

DISPATCH_PERMISSIONS = (
    "subcontract_dispatch.read.all",
    "subcontract_dispatch.create.all",
    "subcontract_dispatch.edit.all",
)


class DispatchCase(ResultCase):
    """Lead can also be tested by three subcontractors; Coastal's accreditation has expired. The head of the department
    outsources the lead test, which no machine can finish in time, and the sample delivery staff carry it; a person of
    Northern signs in to the portal, and so does a person of Southern."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.northern, cls.southern, cls.coastal = cls.env[MODEL_SUBCONTRACTOR].create(
            [
                {"name": "Northern Testing Laboratory"},
                {"name": "Southern Microbiology Centre"},
                {"name": "Coastal Analytical Services"},
            ]
        )
        cls.northern_way, cls.southern_way, cls.coastal_way = cls.env[MODEL_PARAMETER_METHOD].create(
            [
                {
                    "parameter_id": cls.parameter.id,
                    "method_id": cls.method.id,
                    "subcontractor_id": subcontractor.id,
                }
                for subcontractor in (cls.northern, cls.southern, cls.coastal)
            ]
        )
        for way in (cls.northern_way, cls.southern_way, cls.coastal_way):
            cls.offer(cls.parameter, cls.sample_type, way)
        cls.coastal.accreditation_expiry = "2026-01-31"
        cls.grant(cls.head, *DISPATCH_PERMISSIONS)
        cls.delivery_role = cls.env[MODEL_ROLE].create({"code": "dispatch_courier", "name": "Sample delivery staff"})
        cls.env["ir.config_parameter"].sudo().set_int(SAMPLE_DELIVERY_ROLE_PARAMETER, cls.delivery_role.id)
        cls.courier = cls.create_person("Vo Thi Giang", login="giang.vo", roles=cls.delivery_role)
        cls.northern_user = cls.portal_user(cls.northern, "Nguyen Thi Lan", "lan.nguyen")
        cls.southern_user = cls.portal_user(cls.southern, "Le Thi Hoa", "hoa.le")
        cls.test.outsourcing_suggested = True

    @classmethod
    def portal_user(cls, subcontractor, name, login):
        contact = cls.env["res.partner"].create({"name": name, "parent_id": subcontractor.partner_id.id})
        return cls.env["res.users"].create(
            {
                "login": login,
                "partner_id": contact.id,
                "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
            }
        )

    def outsource(self, test=None, way=None):
        return self.as_person(test or self.test, self.head)._accept_outsourcing(way or self.northern_way)

    def send_dispatch(self, dispatch):
        dispatch = self.as_person(dispatch, self.head)
        dispatch.write({"sent_date": "2026-10-12", "expected_date": "2026-10-16", "courier_id": self.courier.id})
        dispatch.action_send()
        return dispatch

    def enter_on_portal(self, dispatch, value="", value_text="", user=None):
        user = user or self.northern_user
        dispatches = self.env[MODEL_SUBCONTRACT_DISPATCH].with_user(user)._portal_dispatches(user, dispatch.id)
        return dispatches._portal_enter_result(self.test.id, value, value_text)

    def send_portal_result(self, result):
        """The lab QA sets the conclusion against the regulation and sends the subcontractor's result."""
        self.as_person(result, self.tester).conclusion = "pass"
        self.send(result)

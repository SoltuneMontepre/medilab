from odoo.fields import Command

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_PERMISSION, MODEL_TASK
from odoo.addons.sol_laboratory.services.record_id import persisted_id

SUPPORT_PERMISSIONS = ("support.request.read.all", "support.request.create.all", "support.request.edit.all")
COMMENT = "comment"


class SupportCase(OrderCase):
    """Salespeople who handle support, and a second customer with a portal user of their own."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        permissions = cls.env[MODEL_PERMISSION].search([("code", "in", SUPPORT_PERMISSIONS)])
        for person in (cls.sales_person, cls.other_person, cls.head_person):
            person.permission_ids |= permissions
        cls.other_customer = cls.env["res.partner"].create({"name": "Cong ty Khac", "is_company": True})
        cls.other_contact = cls.env["res.partner"].create(
            {"name": "Le Thi Khac", "parent_id": cls.other_customer.id, "email": "khac@khac.example"}
        )
        cls.other_portal = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Le Thi Khac",
                    "login": "portal.khac",
                    "partner_id": cls.other_contact.id,
                    "group_ids": [Command.set([persisted_id(cls.env.ref("base.group_portal"))])],
                }
            )
        )
        cls.env[MODEL_CUSTOMER].create({"partner_id": cls.other_customer.id})

    def open_request(self, subject="Where are my results?", order=None, user=None, body="Please help."):
        requests = self.env[MODEL_SUPPORT_REQUEST].with_user(user or self.portal)
        return requests.portal_open(subject, order.id if order else None, body)

    def write_on(self, request, user, body, subtype="mail.mt_comment"):
        return request.with_user(user).message_post(body=body, message_type=COMMENT, subtype_xmlid=subtype)

    def tasks_of(self, request):
        return self.env[MODEL_TASK].search([("document_model", "=", request._name), ("document_id", "=", request.id)])

    def todo(self, user):
        return (
            self.env[MODEL_TASK]
            .with_user(user)
            .search([("is_mine", "=", True), ("status", "in", ("assigned", "in_progress"))])
        )

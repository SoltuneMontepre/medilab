from odoo.fields import Command

from odoo.addons.commerce.constants.models import MODEL_INVOICE
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION
from odoo.addons.laboratory.tests.people_case import PeopleCase

ACCOUNTANT_PERMISSIONS = (
    "invoice.read.all",
    "invoice.create.all",
    "invoice.edit.all",
    "invoice.delete.all",
    "invoice.line.read.all",
    "invoice.line.create.all",
    "invoice.line.edit.all",
    "invoice.line.delete.all",
)
SALES_PERMISSIONS = ("invoice.read.all", "invoice.line.read.all")


class InvoicingCase(PeopleCase):
    """A customer, an accountant who holds every invoice permission and a salesperson who reads invoices."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create(
            {"name": "Công ty TNHH Thực phẩm Sao Mai", "vat": "0312345678", "email": "ketoan@saomai.example"}
        )
        cls.accountant = cls.create_person("Le Thi Kim", login="kim.le", permissions=ACCOUNTANT_PERMISSIONS)
        cls.salesperson = cls.create_person("Pham Van Nam", login="nam.pham", permissions=SALES_PERMISSIONS)

    @classmethod
    def permissions(cls, *codes):
        # Permissions of several modules: found by code rather than by the laboratory external id.
        return cls.env[MODEL_PERMISSION].search([("code", "in", codes)])

    @classmethod
    def create_invoice(cls, lines=((5_000_000, 0),), kind="final", post=True, partner=None, **vals):
        invoice = cls.env[MODEL_INVOICE].create(
            {
                "partner_id": (partner or cls.customer).id,
                "kind": kind,
                "line_ids": [
                    Command.create({"description": f"Line {index + 1}", "amount_untaxed": amount, "tax_rate": rate})
                    for index, (amount, rate) in enumerate(lines)
                ],
                **vals,
            }
        )
        if post:
            invoice.action_post()
        return invoice

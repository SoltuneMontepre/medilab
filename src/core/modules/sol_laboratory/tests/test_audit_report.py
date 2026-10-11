import io
import zipfile
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_REPORT, MODEL_CHEMICAL
from odoo.addons.sol_laboratory.constants.xml_ids import AUDIT_REPORT_ACTION


@tagged("post_install", "-at_install")
class TestAuditReport(AuditCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env["res.users"].with_user(cls.auditor))
        chemical = cls.env[MODEL_CHEMICAL].create({"code": "HC-102", "name": "Hydrochloric acid 37%"})
        cls.chemical_name = chemical.display_name
        chemical.unlink()
        cls.limit._audit("sign")
        cls.regulation._audit("approve")

    def report(self, **vals):
        return (
            self.env[MODEL_AUDIT_REPORT]
            .with_user(self.auditor)
            .create({"date_from": self.today, "date_to": self.today, **vals})
        )

    def test_a_report_for_the_period_lists_every_signature_approval_and_deletion(self):
        rows = self.report()._rows()

        self.assertTrue({"Sign", "Approve", "Delete"} <= {row["action"] for row in rows})
        self.assertIn(self.chemical_name, [row["note"] for row in rows if row["action"] == "Delete"])

    def test_a_report_leaves_out_other_periods(self):
        yesterday = self.today - timedelta(days=1)

        self.assertFalse(self.report(date_from=yesterday, date_to=yesterday)._rows())

    def test_a_report_is_filtered_like_the_trail(self):
        rows = self.report(action="sign")._rows()

        self.assertEqual({(row["action"], row["document"]) for row in rows}, {("Sign", self.limit.display_name)})

    def test_one_row_per_change_and_one_per_entry_without_changes(self):
        self.limit.write({"max_value": 0.02, "decimals": 2})

        rows = self.report(document_model=self.limit._name, action="edit")._rows()

        self.assertEqual(
            sorted((row["field"], row["old_value"], row["new_value"]) for row in rows),
            [("Decimals", "3", "2"), ("Maximum", "0.01", "0.02")],
        )
        self.assertEqual(len(self.report(action="sign")._rows()), 1)

    def test_the_report_prints_and_exports(self):
        report = self.report()
        # An administrator of a company without a document layout prints without setting one up first.
        action = self.env[MODEL_AUDIT_REPORT].create({"date_from": self.today, "date_to": self.today}).action_print()

        html, _type = self.env["ir.actions.report"]._render_qweb_html(AUDIT_REPORT_ACTION, report.ids)
        report.action_export()

        self.assertEqual(action["type"], "ir.actions.report")
        self.assertIn(self.chemical_name, html.decode())
        with zipfile.ZipFile(io.BytesIO(report.file.content)) as workbook:
            self.assertIn(self.chemical_name, workbook.read("xl/sharedStrings.xml").decode())

from pathlib import Path
from unittest.mock import patch

from odoo.fields import Command
from odoo.modules.module import load_script
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_ROLE, MODEL_TEST_REPORT

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.42.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestReportPermissionMigration(PeopleCase):
    def test_holders_of_the_report_edit_permission_deliver_reports_and_the_permission_goes(self):
        reports = type(self.env[MODEL_TEST_REPORT])
        with patch.object(reports, "_permission_actions", ("read", "edit", "sign", "deliver")):
            edit = self.env[MODEL_PERMISSION].create(
                {"name": "Edit test reports", "document_model": MODEL_TEST_REPORT, "action": "edit"}
            )
        edit_id = edit.id
        self.assertIsInstance(edit_id, int)
        role = self.env[MODEL_ROLE].create(
            {"code": "report_editor", "name": "Report editor", "permission_ids": [Command.link(edit_id)]}
        )
        person = self.create_person("Ly Thi Mai", self.chemistry)
        person.permission_ids = [Command.link(edit_id)]
        group = edit.group_id

        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.41.0")

        self.env.invalidate_all()
        deliver = self.permissions("test_report.deliver.all")
        self.assertFalse(edit.exists())
        self.assertFalse(group.exists())
        self.assertEqual(role.permission_ids, deliver)
        self.assertEqual(person.permission_ids, deliver)
        remaining = self.env[MODEL_PERMISSION].search(
            [("document_model", "=", MODEL_TEST_REPORT), ("action", "=", "edit")]
        )
        self.assertFalse(remaining)

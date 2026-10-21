import uuid

from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import RAW_DATA, RESULT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_LABORATORY_FOLDER,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_REQUEST,
)

# Created without chatter entries, so removing the records leaves nothing behind.
QUIET = {"tracking_disable": True, "mail_create_nolog": True, "mail_notrack": True}


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderConcurrency(LaboratoryFilesConcurrencyCase):
    """Two real database transactions creating the folders of one sample at once, the second one through Odoo's request
    retrying."""

    def setUp(self):
        super().setUp()
        self.ids = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        env = env(context=QUIET)
        customer = env[MODEL_CUSTOMER].create({"name": f"Concurrency {uuid.uuid4().hex[:8]}", "is_company": True})
        sample_type = env[MODEL_SAMPLE_TYPE].create({"name": f"Concurrency {uuid.uuid4().hex[:8]}"})
        request = env[MODEL_TEST_REQUEST].create(
            {
                "customer_id": customer.id,
                "expected_date": "2026-10-20",
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": "Lavie bottled water 1 L",
                            "sample_type_id": sample_type.id,
                            "physical_state": "liquid",
                        }
                    )
                ],
            }
        )
        return {
            "customer": customer.id,
            "partner": customer.partner_id.id,
            "sample_type": sample_type.id,
            "request": request.id,
            "sample": request.sample_ids.id,
        }

    def remove(self, env):
        # Folders, samples and requests refuse deletion, so the data these tests committed is removed with SQL.
        cr = env.cr
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute(
            "DELETE FROM medilab_laboratory_folder_member WHERE folder_id IN "
            "(SELECT id FROM medilab_laboratory_folder WHERE sample_id = %s)",
            [self.ids["sample"]],
        )
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE sample_id = %s", [self.ids["sample"]])
        cr.execute("DELETE FROM medilab_sample WHERE id = %s", [self.ids["sample"]])
        cr.execute("DELETE FROM medilab_test_request WHERE id = %s", [self.ids["request"]])
        cr.execute("DELETE FROM medilab_sample_type WHERE id = %s", [self.ids["sample_type"]])
        cr.execute("DELETE FROM medilab_customer WHERE id = %s", [self.ids["customer"]])
        cr.execute("DELETE FROM res_partner WHERE id = %s", [self.ids["partner"]])

    def create_folders(self, env):
        folders = env[MODEL_SAMPLE].browse(self.ids["sample"])._create_laboratory_folders(env.ref("base.user_admin"))
        return env[MODEL_SAMPLE].browse(self.ids["sample"]) if not folders else folders[:1]

    def test_two_creations_of_a_samples_folders_at_once_make_one_folder_of_each_category(self):
        attempts, _second = self.race(self.create_folders, self.create_folders)

        def work(env):
            folders = env[MODEL_LABORATORY_FOLDER].search([("sample_id", "=", self.ids["sample"])])
            return sorted(folders.mapped("category"))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), sorted([RAW_DATA, RESULT]))

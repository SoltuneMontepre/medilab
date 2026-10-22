from types import SimpleNamespace

from odoo.exceptions import ConcurrencyError
from odoo.http import retrying
from odoo.tests import tagged
from odoo.tools import mute_logger

from .audit_case import AuditLookup
from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE


@tagged("post_install", "-at_install")
class TestLaboratoryFileHistoryRetrying(AuditLookup, LaboratoryApiCase):
    """Odoo's request retrying inside real requests of restoring and downloading: a request that fails on concurrency
    after its work runs again, and its version and its audit entry count once."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = cls.new_auditor()

    def setUp(self):
        super().setUp()
        # Odoo waits a random time before each new try; these tests do not.
        self.patch(retrying, "random", SimpleNamespace(uniform=lambda _low, _high: 0))
        self.key = self.signed_in_key(self.tester, "hplc-installation")
        self.file = self.file_of("HPLC/run-01.csv")
        self.first = self.save(self.file, "run 1")
        self.save(self.file, "run 2")
        self.path = f"/folders/{self.folder.id}/files/{self.file.id}/versions/{self.first.id}"

    def fail_after(self, method_name):
        """Make the file's method fail on concurrency once it has done its work, on its first run only."""
        files = type(self.env[MODEL_LABORATORY_FILE])
        method = getattr(files, method_name)
        runs = []

        def failing(*args, **kwargs):
            result = method(*args, **kwargs)
            runs.append(1)
            if len(runs) == 1:
                raise ConcurrencyError("A concurrent request changed the same records.")
            return result

        self.patch(files, method_name, failing)
        return runs

    def test_a_restore_run_again_adds_one_version(self):
        runs = self.fail_after("_restore")

        with mute_logger("odoo.http"):
            response = self.api("POST", f"{self.path}/restore", key=self.key)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(runs), 2)
        self.assertEqual(self.file.version_ids.mapped("number"), [3, 2, 1])
        self.assertEqual(len(self.entries(self.file.current_version_id, "create")), 1)

    def test_a_download_run_again_is_recorded_once(self):
        runs = self.fail_after("_download_address")

        with mute_logger("odoo.http"):
            response = self.api("POST", f"{self.path}/download", key=self.key)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(self.entries(self.file, "download")), 1)

import hashlib
import uuid

from odoo.tests import tagged

from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import DUPLICATE, VERIFIED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT


@tagged("post_install", "-at_install")
class TestLaboratoryContentConcurrency(LaboratoryFilesConcurrencyCase):
    """Two contents of the same bytes settled at once, in real database transactions, the second through Odoo's request
    retrying."""

    def setUp(self):
        super().setUp()
        data = f"Kết quả HPLC {uuid.uuid4().hex}".encode()
        self.sha256, self.size = hashlib.sha256(data).hexdigest(), len(data)
        self.addCleanup(self.committed, self.remove)

    def remove(self, env):
        # Content refuses deletion, so what these tests committed is removed with SQL.
        env.cr.execute("DELETE FROM medilab_laboratory_content WHERE sha256 = %s", [self.sha256])

    def settle(self, env):
        return env[MODEL_LABORATORY_CONTENT]._new_pending()._settle(self.sha256, self.size)

    def test_two_contents_of_the_same_bytes_settled_at_once_keep_one_verified(self):
        attempts, canonical_id = self.race(self.settle, self.settle)

        def work(env):
            contents = env[MODEL_LABORATORY_CONTENT].search([("sha256", "=", self.sha256)], order="id")
            return [(content.id, content.state) for content in contents]

        contents = self.committed(work)
        self.assertEqual(attempts, 2)
        self.assertEqual([state for _id, state in contents], [VERIFIED, DUPLICATE])
        self.assertEqual(canonical_id, contents[0][0])

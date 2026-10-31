import uuid

from odoo.tests import new_test_user, tagged

from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_EXISTS
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestLaboratoryFolderApiConcurrency(LaboratoryFilesConcurrencyCase):
    """Two requests of the laboratory files API changing one folder at once, in real database transactions, the second
    one through Odoo's request retrying."""

    def setUp(self):
        super().setUp()
        self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.suffix = uuid.uuid4().hex[:8]
        groups = f"base.group_user,{LABORATORY_FILES_GROUP}"
        owner, member = (
            new_test_user(env, login=f"race.{name}.{self.suffix}", groups=groups) for name in ("owner", "member")
        )
        self.owner_id, self.member_id = owner.id, member.id
        device = env[MODEL_LABORATORY_DEVICE].create(
            {"user_id": owner.id, "client_uid": f"race-{self.suffix}", "name": "race", "platform": "linux"}
        )
        self.device_id = device.id
        self.folder_id = env[MODEL_LABORATORY_FOLDER].with_user(owner).create({"name": f"Shared {self.suffix}"}).id

    def remove(self, env):
        # Folders and computers are never deleted, so what these tests committed is removed with SQL, the audit entries
        # of the people's contacts among it.
        cr = env.cr
        cr.execute("DELETE FROM medilab_audit_change WHERE entry_id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("SELECT id FROM medilab_laboratory_folder WHERE owner_id = %s", [self.owner_id])
        folder_ids = [folder_id for (folder_id,) in cr.fetchall()]
        cr.execute("DELETE FROM medilab_laboratory_sync_rule WHERE folder_id = ANY(%s)", [folder_ids])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = ANY(%s)", [folder_ids])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = ANY(%s)", [folder_ids])
        cr.execute("DELETE FROM medilab_laboratory_device WHERE id = %s", [self.device_id])
        users = env[MODEL_RES_USERS].browse([self.owner_id, self.member_id])
        partners = users.partner_id
        users.unlink()
        partners.unlink()

    def folder(self, env):
        return env[MODEL_LABORATORY_FOLDER].browse(self.folder_id).with_user(self.owner_id)

    def create_folder(self, key):
        def create(env):
            device = env[MODEL_LABORATORY_DEVICE].browse(self.device_id).with_user(self.owner_id)
            return env[MODEL_LABORATORY_FOLDER].with_user(self.owner_id)._create_for_device(device, "Runs", key)

        return create

    def count(self, model, domain):
        return self.committed(lambda env: env[model].search_count(domain))

    def test_two_creations_with_one_idempotency_key_at_once_make_one_folder(self):
        attempts, second = self.race(self.create_folder("create-runs"), self.create_folder("create-runs"))

        self.assertEqual(attempts, 2)
        self.assertEqual(
            self.count(MODEL_LABORATORY_FOLDER, [("owner_id", "=", self.owner_id), ("root", "=", "Runs")]), 1
        )
        self.assertEqual(
            self.committed(
                lambda env: (
                    env[MODEL_LABORATORY_FOLDER].search([("root", "=", "Runs"), ("owner_id", "=", self.owner_id)]).id
                )
            ),
            second,
        )

    def test_two_creations_of_one_name_without_a_key_at_once_refuse_the_second(self):
        attempts, refusal = self.race(self.create_folder(None), self.create_folder(None))

        self.assertEqual(attempts, 2)
        self.assertEqual(assert_instance(refusal, LaboratoryFileError).code, FOLDER_EXISTS)

    def test_two_additions_of_one_member_at_once_make_one_membership(self):
        def add(env):
            return self.folder(env)._add_member(self.member_id)

        attempts, _second = self.race(add, add)

        domain = [("folder_id", "=", self.folder_id), ("user_id", "=", self.member_id)]
        self.assertEqual(attempts, 2)
        self.assertEqual(self.count(MODEL_LABORATORY_FOLDER_MEMBER, domain), 1)

    def test_two_additions_of_one_rule_at_once_make_one_rule(self):
        def add(env):
            return self.folder(env)._add_rule("extension", "CSV", True)

        attempts, _second = self.race(add, add)

        self.assertEqual(attempts, 2)
        self.assertEqual(self.count(MODEL_LABORATORY_SYNC_RULE, [("folder_id", "=", self.folder_id)]), 1)

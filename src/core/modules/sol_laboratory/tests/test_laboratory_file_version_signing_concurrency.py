import uuid

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .laboratory_files_case import stored_content
from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING, STATE_APPROVED, STATE_NONE
from odoo.addons.sol_laboratory.constants.laboratory_files import NOT_FOUND, RESULT, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
    MODEL_RES_USERS,
    MODEL_ROLE,
    MODEL_SIGNATURE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_PERSON, LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


def save(file, content):
    return file._add_version(
        content=stored_content(file.env, content), source=SYNCED, user=file.env.ref("base.user_admin")
    )


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersionSigningConcurrency(LaboratoryFilesConcurrencyCase):
    """Two real database transactions signing and saving one result file of a sample at once, the second one through
    Odoo's request retrying. The administrator signs at the one level of the chain of file versions."""

    def setUp(self):
        super().setUp()
        self.ids = self.committed(self.prepare)
        self.addCleanup(self.committed, self.remove)
        # In a transaction of its own: removing a person tracks their contact, which fails among the other removals.
        self.addCleanup(self.committed, self.remove_outsider)

    def prepare(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        self.last_entry_id = env.cr.fetchone()[0]
        self.last_content_id = self.last_content(env)
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_signature")
        self.last_signature_id = env.cr.fetchone()[0]
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_document_lock")
        self.last_lock_id = env.cr.fetchone()[0]
        chain = env[MODEL_APPROVAL_CHAIN].search(
            [("document_model", "=", MODEL_LABORATORY_FILE_VERSION), ("purpose", "=", PURPOSE_SIGNING)]
        )
        created_chain = not chain
        if created_chain:
            chain = chain.create(
                {"document_model": MODEL_LABORATORY_FILE_VERSION, "purpose": PURPOSE_SIGNING, "name": "File signing"}
            )
            env[MODEL_APPROVAL_LEVEL].create(
                {
                    "chain_id": chain.id,
                    "sequence": 10,
                    "name": "Head of department",
                    "role_id": env[MODEL_ROLE].create({"code": f"qa_{uuid.uuid4().hex[:8]}", "name": "Signer"}).id,
                }
            )
        administrator = env.ref(ADMINISTRATOR_PERSON)
        added_roles = chain.level_ids.role_id - administrator.role_ids
        administrator.role_ids |= added_roles
        sample = self.create_sample(env)
        folder = env[MODEL_LABORATORY_FOLDER].create(
            {
                "name": f"Concurrency {uuid.uuid4().hex[:8]}",
                "owner_id": env.ref("base.user_admin").id,
                "sample_id": sample["sample"],
                "category": RESULT,
            }
        )
        file = env[MODEL_LABORATORY_FILE]._get_or_create(folder, "lead.xlsx")
        # Holds the laboratory files permission but is no member of the folder.
        outsider = new_test_user(
            env, login=f"sign.outsider.{uuid.uuid4().hex[:8]}", groups=f"base.group_user,{LABORATORY_FILES_GROUP}"
        )
        return {
            "outsider": outsider.id,
            "chain": chain.id if created_chain else False,
            "roles": added_roles.ids,
            "sample": sample,
            "folder": folder.id,
            "file": file.id,
            "first": save(file, "lead 0.004 mg/L").id,
        }

    def remove(self, env):
        # Signatures, files, versions and changes refuse deletion, so the data these tests committed is removed with SQL.
        cr = env.cr
        cr.execute("DELETE FROM medilab_signature WHERE id > %s", [self.last_signature_id])
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_document_lock WHERE id > %s", [self.last_lock_id])
        cr.execute("DELETE FROM medilab_laboratory_file_change WHERE folder_id = %s", [self.ids["folder"]])
        cr.execute("UPDATE medilab_laboratory_file SET current_version_id = NULL WHERE id = %s", [self.ids["file"]])
        cr.execute("DELETE FROM medilab_laboratory_file_version WHERE file_id = %s", [self.ids["file"]])
        self.remove_contents(cr, self.last_content_id)
        cr.execute("DELETE FROM medilab_laboratory_file WHERE id = %s", [self.ids["file"]])
        cr.execute("DELETE FROM medilab_laboratory_folder_member WHERE folder_id = %s", [self.ids["folder"]])
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE id = %s", [self.ids["folder"]])
        self.remove_sample(cr, self.ids["sample"])
        administrator = env.ref(ADMINISTRATOR_PERSON)
        administrator.role_ids -= env[MODEL_ROLE].browse(self.ids["roles"])
        if self.ids["chain"]:
            chain = env[MODEL_APPROVAL_CHAIN].browse(self.ids["chain"])
            roles = chain.level_ids.role_id
            chain.unlink()
            roles.unlink()

    def remove_outsider(self, env):
        outsider = env[MODEL_RES_USERS].browse(self.ids["outsider"])
        partner = outsider.partner_id
        outsider.unlink()
        partner.unlink()

    def first_version(self, env):
        return env[MODEL_LABORATORY_FILE_VERSION].browse(self.ids["first"]).with_user(env.ref("base.user_admin"))

    def sign_first(self, env):
        version = self.first_version(env)
        version.action_sign()
        return version

    def state(self):
        def work(env):
            file = env[MODEL_LABORATORY_FILE].browse(self.ids["file"])
            versions = file.version_ids.sorted("number")
            signatures = env[MODEL_SIGNATURE].search(
                [("document_model", "=", MODEL_LABORATORY_FILE_VERSION), ("document_id", "in", versions.ids)]
            )
            return [(version.number, version.approval_state) for version in versions], len(signatures)

        return self.committed(work)

    def test_a_signature_that_comes_after_a_newer_version_is_refused(self):
        attempts, refusal = self.race(
            lambda env: save(env[MODEL_LABORATORY_FILE].browse(self.ids["file"]), "lead 0.005 mg/L"), self.sign_first
        )

        self.assertEqual(attempts, 2)
        self.assertIsInstance(refusal, UserError)
        self.assertEqual(self.state(), ([(1, STATE_NONE), (2, STATE_NONE)], 0))

    def test_a_save_that_comes_after_a_signature_adds_an_unsigned_version(self):
        attempts, _version = self.race(
            self.sign_first, lambda env: save(env[MODEL_LABORATORY_FILE].browse(self.ids["file"]), "lead 0.005 mg/L")
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, STATE_APPROVED), (2, STATE_NONE)], 1))

    def test_someone_who_may_not_sign_is_refused_without_waiting_for_a_save(self):
        def sign_as_outsider(env):
            version = env[MODEL_LABORATORY_FILE_VERSION].browse(self.ids["first"]).with_user(self.ids["outsider"])
            version.action_sign()
            return version

        attempts, refusal = self.race(
            lambda env: save(env[MODEL_LABORATORY_FILE].browse(self.ids["file"]), "lead 0.005 mg/L"), sign_as_outsider
        )

        self.assertEqual(attempts, 1)
        self.assertIsInstance(refusal, LaboratoryFileError)
        self.assertEqual(assert_instance(refusal, LaboratoryFileError).code, NOT_FOUND)
        self.assertEqual(self.state(), ([(1, STATE_NONE), (2, STATE_NONE)], 0))

    def test_signing_twice_at_once_records_one_signature(self):
        attempts, refusal = self.race(self.sign_first, self.sign_first)

        self.assertEqual(attempts, 2)
        self.assertIsInstance(refusal, UserError)
        self.assertEqual(self.state(), ([(1, STATE_APPROVED)], 1))

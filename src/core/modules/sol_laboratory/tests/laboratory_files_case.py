import hashlib

from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_KEY_SCOPE, MEMBER_ROLE, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
    MODEL_RES_USERS_APIKEYS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP, LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

PASSWORD = "Phong-thi-nghiem-2026"


class LaboratoryFilesCase(TransactionCase):
    """Two testers with the laboratory files permission, a colleague without it and an administrator. The tester owns
    the HPLC folder, which the second tester is a member of."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester = cls.create_user("lab.tester", LABORATORY_FILES_GROUP)
        cls.member = cls.create_user("lab.member", LABORATORY_FILES_GROUP)
        cls.outsider = cls.create_user("lab.outsider", LABORATORY_FILES_GROUP)
        cls.colleague = cls.create_user("lab.colleague")
        cls.administrator = cls.create_user("lab.administrator", ADMINISTRATOR_GROUP)
        cls.folder = cls.env[MODEL_LABORATORY_FOLDER].create(
            {
                "name": "HPLC",
                "owner_id": cls.tester.id,
                "member_ids": [Command.create({"user_id": cls.member.id, "role": MEMBER_ROLE})],
            }
        )

    @classmethod
    def create_user(cls, login, *groups):
        return new_test_user(cls.env, login=login, password=PASSWORD, groups=",".join(("base.group_user", *groups)))

    def sign_in(self, user, client_uid, name="HPLC-PC", platform="windows"):
        """Sign a computer of the user in, as Medilab Sync does: the device and its key."""
        return self.env[MODEL_LABORATORY_DEVICE]._sign_in(user.login, PASSWORD, client_uid, name, platform)

    def device_of(self, key):
        """The computer a call with the key comes from, as the laboratory files API finds it after Odoo verified the
        key."""
        uid = self.env[MODEL_RES_USERS_APIKEYS]._check_credentials(scope=DEVICE_KEY_SCOPE, key=key)
        if not uid:
            self.fail("Odoo refused the key.")
        return self.env[MODEL_LABORATORY_DEVICE].with_user(uid)._from_key(key)

    def assertRefused(self, code, call, *args):
        with self.assertRaises(LaboratoryFileError) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)

    @staticmethod
    def sha(content):
        return hashlib.sha256(content.encode()).hexdigest()

    def file_of(self, path, folder=None):
        return self.env[MODEL_LABORATORY_FILE]._get_or_create(folder or self.folder, path)

    def save(self, file, content, user=None, source=SYNCED, **values):
        """Store the content as a version of the file, as a save from a computer does once its bytes are stored."""
        return file._add_version(
            sha256=self.sha(content),
            size=len(content),
            storage_key=f"test/{self.sha(content)}",
            source=source,
            user=user or self.tester,
            **values,
        )

import hashlib

from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FILE_VERSION,
)
from odoo.addons.sol_laboratory.models.laboratory_files.laboratory_file_version import PROTECTED_FIELDS

FIVE_GIB = 5 * 2**30


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersionImmutability(LaboratoryFilesCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.file = cls.env[MODEL_LABORATORY_FILE].create({"folder_id": cls.folder.id, "path": "HPLC/run-01.csv"})
        cls.version = cls.create_version(cls.file, 1, "run 1")

    @classmethod
    def create_version(cls, file, number, content, **values):
        """A version created directly, of verified content of the text; values replace what the version records."""
        data = content.encode()
        size = values.get("size", len(data))
        sha256 = hashlib.sha256(data).hexdigest()
        stored = cls.env[MODEL_LABORATORY_CONTENT].sudo()._new_pending()._settle(sha256, max(size, 0))
        return cls.env[MODEL_LABORATORY_FILE_VERSION].create(
            {
                "file_id": file.id,
                "number": number,
                "source": SYNCED,
                "size": size,
                "sha256": sha256,
                "content_id": stored.id,
                "user_id": cls.tester.id,
                **values,
            }
        )

    def test_no_one_changes_a_version_or_deletes_it(self):
        changes = {
            "file_id": self.env[MODEL_LABORATORY_FILE].create({"folder_id": self.folder.id, "path": "other.csv"}).id,
            "number": 7,
            "parent_version_id": self.version.id,
            "restored_from_id": self.version.id,
            "source": CONFLICT,
            "size": 1,
            "sha256": "0" * 64,
            "content_id": self.stored("other").id,
            "user_id": self.member.id,
            "device_id": False,
            "idempotency_key": "another-request",
        }
        self.assertEqual(set(changes), set(PROTECTED_FIELDS))

        for version in (self.version, self.version.with_user(self.administrator)):
            for field_name, value in changes.items():
                with self.subTest(user=version.env.user.login, field=field_name), self.assertRaises(UserError):
                    version.write({field_name: value})
            with self.assertRaises(UserError):
                version.unlink()

    def test_a_file_has_one_version_of_each_number(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_version(self.file, 1, "run 1 again")

    def test_a_hash_is_64_lowercase_hexadecimal_digits_and_a_size_is_never_negative(self):
        refused = ({"sha256": "A" * 64}, {"sha256": "a" * 63}, {"sha256": "g" * 64}, {"size": -1})
        for number, values in enumerate(refused, start=2):
            with (
                self.subTest(values=values),
                self.assertRaises(IntegrityError),
                mute_logger("odoo.sql_db"),
                self.env.cr.savepoint(),
            ):
                self.create_version(self.file, number, "run", **values)

    def test_a_size_beyond_two_gibibytes_is_kept_read_and_summed(self):
        version = self.create_version(self.file, 2, "large", size=FIVE_GIB)
        version.invalidate_recordset(["size"])
        self.env.cr.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'medilab_laboratory_file_version' AND column_name = 'size'"
        )

        self.assertEqual(self.env.cr.fetchall(), [("bigint",)])
        self.assertEqual(version.size, FIVE_GIB)
        self.assertEqual(version.read(["size"])[0]["size"], FIVE_GIB)
        versions = self.env[MODEL_LABORATORY_FILE_VERSION]
        [(file, total)] = versions._read_group([("id", "=", version.id)], ["file_id"], ["size:sum"])
        self.assertEqual((file, total), (self.file, FIVE_GIB))
        grouped = versions.web_read_group([("id", "=", version.id)], ["file_id"], ["size:sum"])
        self.assertEqual(grouped["groups"][0]["size:sum"], FIVE_GIB)

    def test_the_changes_of_a_folder_are_never_changed_or_deleted(self):
        change = self.env[MODEL_LABORATORY_FILE_CHANGE].create(
            {"folder_id": self.folder.id, "file_id": self.file.id, "version_id": self.version.id}
        )

        with self.assertRaises(UserError):
            change.write({"version_id": self.version.id})
        with self.assertRaises(UserError):
            change.unlink()

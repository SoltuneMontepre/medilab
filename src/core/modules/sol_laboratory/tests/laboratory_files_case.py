from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP, LABORATORY_FILES_GROUP


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
        return new_test_user(cls.env, login=login, password=login, groups=",".join(("base.group_user", *groups)))

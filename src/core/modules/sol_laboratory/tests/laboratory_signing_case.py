from odoo.fields import Command

from .laboratory_files_case import LaboratoryFilesCase
from .people_case import PeopleCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, RAW_DATA
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_ROLE,
    MODEL_SIGNATURE,
)

# What a member of a sample's folders needs: the laboratory files permission and the sample.
MEMBER_PERMISSIONS = ("sample.read.all", "laboratory_folder.create.all")
SIGNER_PERMISSIONS = (*MEMBER_PERMISSIONS, "laboratory_file_version.sign.all", "signature.read.all")


class LaboratorySigningCase(LaboratoryFilesCase, RequestCase, PeopleCase):
    """The head of the department that tests the lead sample created its raw-data and result folders, which a tester of
    the department is a member of. The head signs file versions at the one level of their chain."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chain = cls.signing_chain()
        cls.signer_role = cls.chain.level_ids.role_id
        cls.head = cls.create_person(
            "Le Thi Hoa", cls.department, "hoa.head", permissions=SIGNER_PERMISSIONS, roles=cls.signer_role
        )
        cls.department.manager_id = cls.head.employee_id
        cls.saver = cls.create_person("Pham Van Nam", cls.department, "nam.pham", permissions=MEMBER_PERMISSIONS)
        folders = cls.sample._create_laboratory_folders(cls.head.user_id)
        cls.raw_data = folders.filtered(lambda folder: folder.category == RAW_DATA)
        cls.results = folders - cls.raw_data
        for folder in folders:
            folder.member_ids = [Command.create({"user_id": cls.saver.user_id.id, "role": MEMBER_ROLE})]

    @classmethod
    def signing_chain(cls):
        """The chain of file versions with one level, signed by a new role that holds no permission, so a person has
        only the permissions a test gives them. The demo data may have made the chain; its levels take the new role."""
        role = cls.env[MODEL_ROLE].create({"code": "qa_file_signer", "name": "File signer"})
        chains = cls.env[MODEL_APPROVAL_CHAIN]
        chain = chains.search(
            [("document_model", "=", MODEL_LABORATORY_FILE_VERSION), ("purpose", "=", PURPOSE_SIGNING)]
        )
        if chain:
            chain.level_ids.role_id = role
            return chain
        chain = chains.create(
            {"document_model": MODEL_LABORATORY_FILE_VERSION, "purpose": PURPOSE_SIGNING, "name": "File signing"}
        )
        cls.env[MODEL_APPROVAL_LEVEL].create(
            {"chain_id": chain.id, "sequence": 10, "name": "Head of department", "role_id": role.id}
        )
        return chain

    def result_version(self, content="lead 0.004 mg/L", path="lead.xlsx", **values):
        """A version of the results spreadsheet saved by the tester."""
        return self.save(self.file_of(path, self.results), content, user=self.saver.user_id, **values)

    def signatures(self, version):
        return self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", version._name), ("document_id", "=", version.id)], order="id"
        )

from odoo.fields import Command

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.record_id import persisted_id

SAMPLE_READER_GROUP = "sol_laboratory.group_permission_sample_read_all"


class LaboratorySampleFolderCase(LaboratoryFilesCase, RequestCase):
    """The people of LaboratoryFilesCase, of whom the two testers see every sample, as only a sample's folders have a
    category."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.tester | cls.member).group_ids = [Command.link(persisted_id(cls.env.ref(SAMPLE_READER_GROUP)))]

    def folder_of_category(self, category, **vals):
        """A new folder of the tester: of a new sample when it has a category, or of no sample."""
        if category:
            vals |= {"sample_id": self.create_request().sample_ids.id, "category": category}
        return self.env[MODEL_LABORATORY_FOLDER].create({"owner_id": self.tester.id, **vals})

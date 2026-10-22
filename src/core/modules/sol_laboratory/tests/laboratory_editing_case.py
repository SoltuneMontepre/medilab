from .editing_service import use_editing_service
from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_LABORATORY_EDITING_SESSION


class LaboratoryEditingCase(LaboratoryFilesCase):
    """The folders of LaboratoryFilesCase with a results spreadsheet of the HPLC folder the tester saved once."""

    def setUp(self):
        super().setUp()
        self.file = self.file_of("2026/Kết quả HPLC tháng 10.xlsx")
        self.first = self.save(self.file, "Kết quả, bản 1")
        # Opening a file online asks the editing service's health check, which answers up unless a test says otherwise.
        self.health_check = use_editing_service(self)

    def new_session(self, file=None, user=None):
        """A session as opening a file online makes it, without its checks."""
        file = file or self.file
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION].sudo()
        document_key, token_hash = sessions._new_keys()
        return sessions.create(
            {
                "file_id": file.id,
                "base_version_id": file.current_version_id.id,
                "document_key": document_key,
                "callback_token": token_hash,
                "opened_by_id": (user or self.tester).id,
            }
        )

    def entries(self, session, action=None):
        domain = [("document_model", "=", MODEL_LABORATORY_EDITING_SESSION), ("document_id", "=", session.id)]
        if action:
            domain.append(("action", "=", action))
        return self.env[MODEL_AUDIT_ENTRY].sudo().search(domain, order="id")

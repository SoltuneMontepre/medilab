import hmac
import posixpath

from odoo import api, models

from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_CLOSED_UNCHANGED,
    CALLBACK_EDITING,
    CALLBACK_FORCE_SAVE_FAILED,
    CALLBACK_FORCE_SAVED,
    CALLBACK_READY_TO_SAVE,
    CALLBACK_SAVE_FAILED,
    EDITING_UNAVAILABLE,
    SAVED_STATUSES,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION, MODEL_RES_USERS
from odoo.addons.sol_laboratory.services.editing_service_health import is_editing_service_up
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import EditingCallbackRefused, jwt_secret, sign, verify_callback
from odoo.addons.sol_laboratory.services.saved_documents import (
    SavedDocumentRefused,
    SavedDocumentTooLarge,
    SavedDocumentUnavailable,
    saved_document,
)

# The editor of each Office extension.
DOCUMENT_TYPES = {"docx": "word", "xlsx": "cell", "pptx": "slide"}
# Statuses that are only activity: someone is editing, or a force save, which is off.
ACTIVITY_STATUSES = (CALLBACK_EDITING, CALLBACK_FORCE_SAVED, CALLBACK_FORCE_SAVE_FAILED)


# Phiên Chỉnh Sửa Trực Tuyến
class LaboratoryEditingSession(models.Model):
    _inherit = MODEL_LABORATORY_EDITING_SESSION

    @api.model
    def _check_editing_available(self):
        """Refuse with editing_unavailable while the editing service has no secret or does not answer its health
        check."""
        if not jwt_secret() or not is_editing_service_up():
            raise LaboratoryFileError(
                EDITING_UNAVAILABLE,
                self.env._("Online editing is unavailable right now. Syncing, history and restoring still work."),
            )

    def _editor_config(self, user, document_url, callback_url, lifetime_seconds):
        """The editor configuration of the session for the user, signed for lifetime_seconds: the editing service reads
        the base version at document_url and calls back on callback_url. Force save is off."""
        self.ensure_one()
        secret = jwt_secret()
        if not secret:
            raise LaboratoryFileError(EDITING_UNAVAILABLE, self.env._("Online editing is unavailable right now."))
        session = self.sudo()
        path = session.file_id.path
        extension = posixpath.splitext(path)[1].removeprefix(".").lower()
        config = {
            "document": {
                "fileType": extension,
                "key": session.document_key,
                "title": posixpath.basename(path),
                "url": document_url,
                "permissions": {"edit": True},
            },
            "documentType": DOCUMENT_TYPES[extension],
            "editorConfig": {
                "callbackUrl": callback_url,
                "mode": "edit",
                "lang": (user.lang or "en_US").split("_")[0],
                "user": {"id": str(user.id), "name": user.name},
                "customization": {"forcesave": False},
            },
        }
        return {**config, "token": sign(config, secret, lifetime_seconds)}

    @api.model
    def _from_callback(self, callback_token, body, header):
        """The session the editing service calls back for and the fields of its call, once its tokens, its callback
        token and its document key are checked. Raises EditingCallbackRefused otherwise."""
        fields = verify_callback(body, header, jwt_secret())
        session = self._from_callback_token(callback_token)
        key = fields.get("key")
        if not session or not isinstance(key, str):
            raise EditingCallbackRefused("The callback is for no editing session.")
        if not hmac.compare_digest(session.document_key.encode(), key.encode()):
            raise EditingCallbackRefused("The callback's document key is not its session's.")
        return session, fields

    def _receive_callback(self, fields):
        """Act on a checked call of the editing service. True when it is answered with success; false when it is
        answered with an error so it calls back again, which must not roll back what this did. A status the editing
        service never sends is refused."""
        self.ensure_one()
        status = fields.get("status")
        # A JSON true is not a status, though Python takes it for 1.
        if type(status) is not int:
            raise EditingCallbackRefused("The callback has no status.")
        if status in ACTIVITY_STATUSES:
            self._touch()
            return True
        if status == CALLBACK_READY_TO_SAVE:
            return self._receive_save(fields)
        if status == CALLBACK_SAVE_FAILED:
            self._fail(self.env._("The editing service could not save the document."))
            return True
        if status == CALLBACK_CLOSED_UNCHANGED:
            self._close_unchanged()
            return True
        raise EditingCallbackRefused(f"The callback's status {status} is not one the editing service sends.")

    def _receive_save(self, fields):
        """Fetch the saved document and store it as the session's save. A session a save has already ended fetches
        nothing, as this is the editing service repeating a call it got no answer to."""
        self.ensure_one()
        if self.sudo().status in SAVED_STATUSES:
            return True
        editor, editors = self._editors_of(fields)
        try:
            with saved_document(fields.get("url")) as chunks:
                content = self._store_saved_document(chunks)
        except SavedDocumentRefused as error:
            raise EditingCallbackRefused(str(error)) from None
        except SavedDocumentTooLarge:
            self._fail(self.env._("The saved document is over 5 GiB, the largest file kept."))
            return True
        except SavedDocumentUnavailable:
            self._keep_saving()
            return False
        if not editor:
            self._fail(
                self.env._(
                    "The editing service named nobody who can save the file; the saved content is kept under %s.",
                    content["storage_key"],
                )
            )
            return True
        self._store_save(editor=editor, editors=editors, **content)
        return True

    def _store_saved_document(self, chunks):
        """Store the chunks of a saved document as new content and return its sha256, size and storage_key, as
        _store_save() takes them. The laboratory files bucket stores it; without it nothing is stored, and the save
        waits for the editing service to call back again."""
        raise SavedDocumentUnavailable("Saved documents are not stored without the laboratory files bucket.")

    def _editors_of(self, fields):
        """The person who saved, the last one the editing service names, and everyone who changed the document. The
        ids are those of the editor configuration; an id of no active user is left out."""
        users = fields.get("users")
        users = users if isinstance(users, list) else []
        history = fields.get("history")
        changes = history.get("changes") if isinstance(history, dict) else None
        changes = changes if isinstance(changes, list) else []
        changed_by = [
            change["user"].get("id")
            for change in changes
            if isinstance(change, dict) and isinstance(change.get("user"), dict)
        ]
        editor = self._user_of(users[-1] if users else None)
        editors = self.env[MODEL_RES_USERS].sudo().browse()
        for user_id in changed_by:
            editors |= self._user_of(user_id)
        return editor, editors | editor

    def _user_of(self, user_id):
        users = self.env[MODEL_RES_USERS].sudo()
        if not isinstance(user_id, str) or not (user_id.isascii() and user_id.isdigit()):
            return users.browse()
        return users.search([("id", "=", int(user_id))], limit=1)

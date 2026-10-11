import threading
from urllib.parse import urlsplit

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
)

# Odoo's external APIs, and the session route external applications sign in with.
API_PATH_PREFIXES = ("/xmlrpc", "/jsonrpc", "/json/", "/web/session/authenticate")
# Odoo runs a scheduled action with its cron in the context.
CRON_CONTEXT_KEY = "cron_id"
# Logins and logouts are entries on the user who signs in or out.
SESSION_MODEL = "res.users"
POSITIVE_SEARCH_OPERATORS = ("in", "like", "ilike", "=like", "=ilike")


# Mục Nhật Ký Hoạt Động
class AuditEntry(models.Model):
    _name = MODEL_AUDIT_ENTRY
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Audit Entry"
    _order = "create_date desc, id desc"
    # Entries are only read: nobody edits or deletes them.
    _permission_actions = ("read",)

    # The Odoo user who acted; empty when the system acted.
    user_id = fields.Many2one("res.users", readonly=True, ondelete="restrict")
    # Where the action came from: a screen, the API or a scheduled job.
    source = fields.Selection([("screen", "Screen"), ("api", "API"), ("job", "Job")], required=True, readonly=True)
    # The action recorded.
    action = fields.Selection(
        [
            ("login", "Sign In"),
            ("logout", "Sign Out"),
            ("create", "Create"),
            ("edit", "Edit"),
            ("archive", "Archive"),
            ("delete", "Delete"),
            ("approve", "Approve"),
            ("reject", "Reject"),
            ("sign", "Sign"),
            ("withdraw", "Withdraw"),
            ("download", "Download"),
            ("job", "Job"),
            ("integration", "Integration"),
            ("error", "Error"),
        ],
        required=True,
        readonly=True,
    )
    # Technical name of the document acted on.
    document_model = fields.Selection(selection="_selection_document_model", string="Document Type", readonly=True)
    # Id of the document acted on.
    document_id = fields.Integer(string="Document ID", readonly=True)
    # What happened, for actions without field changes, such as the name of a deleted document.
    note = fields.Text(readonly=True)
    # Field changes of the entry.
    change_ids = fields.One2many(MODEL_AUDIT_CHANGE, "entry_id", string="Changes", readonly=True)
    # Name of the document acted on, or the name its delete entry keeps once it is deleted.
    document_name = fields.Char(string="Document", compute="_compute_document_name", search="_search_document_name")

    _document_index = models.Index("(document_model, document_id)")
    _user_date_index = models.Index("(user_id, create_date)")
    _action_date_index = models.Index("(action, create_date)")
    _create_date_index = models.Index("USING brin (create_date)")

    @api.model
    def _selection_document_model(self):
        names = {*self.env.registry[MODEL_AUDIT_MIXIN]._inherit_children, SESSION_MODEL}
        models_ = self.env["ir.model"].sudo().search([("model", "in", list(names))])
        return sorted(((model.model, model.name) for model in models_), key=lambda item: item[1])

    @api.depends("document_model", "document_id")
    def _compute_document_name(self):
        names = {}
        for model, entries in self.grouped("document_model").items():
            if model in self.env:
                documents = self.env[model].sudo().with_context(active_test=False).browse(entries.mapped("document_id"))
                names.update({(model, document.id): document.display_name for document in documents.exists()})
        # A deleted document is named by the name its delete entry keeps.
        missing = self.filtered(lambda entry: (entry.document_model, entry.document_id) not in names)
        deleted = self.sudo().search_fetch(
            Domain("action", "=", "delete")
            & Domain.OR(
                Domain("document_model", "=", model) & Domain("document_id", "in", entries.mapped("document_id"))
                for model, entries in missing.grouped("document_model").items()
            ),
            ["document_model", "document_id", "note"],
        )
        names.update({(entry.document_model, entry.document_id): entry.note for entry in deleted})
        for entry in self:
            entry.document_name = names.get((entry.document_model, entry.document_id), False)

    def _search_document_name(self, operator, value):
        if operator not in POSITIVE_SEARCH_OPERATORS:
            return NotImplemented
        # A deleted document is found by the name its delete entry keeps.
        deleted = self.sudo().search_fetch(
            Domain("action", "=", "delete") & Domain("note", operator, value), ["document_model", "document_id"]
        )
        domains = [
            Domain("document_model", "=", model) & Domain("document_id", "in", entries.mapped("document_id"))
            for model, entries in deleted.grouped("document_model").items()
        ]
        for [model] in self.sudo()._read_group([], ["document_model"]):
            if model not in self.env:
                continue
            documents = self.env[model].sudo().with_context(active_test=False)
            # Odoo cannot search the names of a model without a field that names its records.
            if not (documents._rec_name or documents._rec_names_search):
                continue
            domains.append(
                Domain("document_model", "=", model)
                & Domain("document_id", "in", documents._search([("display_name", operator, value)]))
            )
        return Domain.OR(domains)

    @api.depends("action", "document_model", "document_name")
    def _compute_display_name(self):
        actions = dict(self._fields["action"]._description_selection(self.env))
        for entry in self:
            entry.display_name = " ".join(filter(None, [actions.get(entry.action), entry.document_name or entry.note]))

    def write(self, vals):
        self._refuse_change()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_audit_entry(self):
        raise UserError(self.env._("Audit entries cannot be deleted."))

    def _refuse_change(self):
        raise UserError(self.env._("Audit entries cannot be changed."))

    @api.model
    def _origin_values(self):
        """The source and user of an entry written now."""
        if CRON_CONTEXT_KEY in self.env.context:
            return {"source": "job", "user_id": False}
        uid = self.env.uid
        return {
            "source": "api" if self._request_path().startswith(API_PATH_PREFIXES) else "screen",
            "user_id": uid if uid != SUPERUSER_ID else False,
        }

    @api.model
    def _request_path(self):
        if request:
            return request.httprequest.path
        # Odoo runs XML-RPC and JSON-RPC calls without the request, but the thread serving them keeps its URL.
        return urlsplit(getattr(threading.current_thread(), "url", "")).path

    @api.model
    def _log_session(self, action):
        """Record that the current user signed in or out."""
        self.sudo().create(
            {**self._origin_values(), "action": action, "document_model": SESSION_MODEL, "document_id": self.env.uid}
        )

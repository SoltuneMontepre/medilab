import threading
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.api import SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.sol_laboratory.constants.jobs import JOB_RUN_CONTEXT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_JOB_RUN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
)

# Odoo's external APIs, the session route external applications sign in with, and the routes the Laboratory serves to
# other systems: the mobile app and the Brevo webhook.
API_PATH_PREFIXES = ("/xmlrpc", "/jsonrpc", "/json/", "/web/session/authenticate", "/medilab/")
# Odoo runs a scheduled action with its cron in the context, including crons that are not MediLab jobs.
CRON_CONTEXT_KEY = "cron_id"
POSITIVE_SEARCH_OPERATORS = ("in", "like", "ilike", "=like", "=ilike")


# Mục Nhật Ký Hoạt Động
class AuditEntry(models.Model):
    _name = MODEL_AUDIT_ENTRY
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Audit Entry"
    _order = "create_date desc, id desc"
    # Entries are only read: nobody edits or deletes them.
    _permission_actions = ("read",)

    # The Odoo user who acted; empty when the system or someone not signed in acted.
    user_id = fields.Many2one(MODEL_RES_USERS, readonly=True, ondelete="restrict")
    # Where the action came from: a screen, the API, a scheduled job or the system installing or upgrading a module.
    source = fields.Selection(
        [("screen", "Screen"), ("api", "API"), ("job", "Scheduled Job"), ("system", "System")],
        required=True,
        readonly=True,
    )
    # The action recorded.
    action = fields.Selection(
        [
            ("create", "Create"),
            ("edit", "Edit"),
            ("archive", "Archive"),
            ("delete", "Delete"),
            ("approve", "Approve"),
            ("reject", "Reject"),
            ("sign", "Sign"),
            ("withdraw", "Withdraw"),
            ("download", "Download"),
            ("job", "Job Run"),
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
    # Technical name of the document the one acted on is a part of, such as the test request of a sample.
    parent_model = fields.Selection(selection="_selection_document_model", string="Parent Document Type", readonly=True)
    # Id of the document the one acted on is a part of.
    parent_id = fields.Integer(string="Parent Document ID", readonly=True)
    # The job run that acted, when the source is a job.
    job_run_id = fields.Many2one(MODEL_JOB_RUN, readonly=True, ondelete="restrict")
    # What happened, for actions without field changes, such as the name of a deleted document.
    note = fields.Text(readonly=True)
    # Field changes of the entry.
    change_ids = fields.One2many(MODEL_AUDIT_CHANGE, "entry_id", string="Changes", readonly=True)
    # Name of the document acted on, or the name its delete entry keeps once it is deleted.
    document_name = fields.Char(string="Document", compute="_compute_document_name", search="_search_document_name")

    _document_index = models.Index("(document_model, document_id)")
    _parent_index = models.Index("(parent_model, parent_id) WHERE parent_id IS NOT NULL")
    _user_date_index = models.Index("(user_id, create_date)")
    _action_date_index = models.Index("(action, create_date)")
    _create_date_index = models.Index("USING brin (create_date)")

    @api.model
    def _selection_document_model(self):
        # A model inherits the mixin directly or through another mixin, such as the approval mixin.
        mixin = self.env.registry[MODEL_AUDIT_MIXIN]
        names = [name for name, model in self.env.registry.items() if issubclass(model, mixin) and not model._abstract]
        models_ = self.env["ir.model"].sudo().search([("model", "in", names)])
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
            parts = (actions.get(entry.action), entry.document_name or entry.note)
            entry.display_name = " ".join(part for part in parts if part)

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
        """The source, user and job run of an entry written now."""
        if run_id := self.env.context.get(JOB_RUN_CONTEXT):
            # The user who ran the job by hand, or none for a scheduled run.
            run = self.env[MODEL_JOB_RUN].sudo().browse(run_id)
            return {"source": "job", "user_id": run.triggered_by_id.id, "job_run_id": run.id}
        if self.env.context.get(CRON_CONTEXT_KEY) is not None:
            return {"source": "job", "user_id": False}
        user = self.env.user
        if user.id == SUPERUSER_ID and request and request.session.uid:
            # Odoo's portal reads a customer's documents as the superuser; the person signed in is who acted.
            user = user.browse(request.session.uid)
        if not self.env.registry.ready:
            # Installing or upgrading a module writes its data, such as shipped permissions, before the registry is ready.
            source = "system"
        elif self._request_path().startswith(self._api_path_prefixes()):
            source = "api"
        else:
            source = "screen"
        return {"source": source, "user_id": user.id if user.id != SUPERUSER_ID and not user._is_public() else False}

    @api.model
    def _api_path_prefixes(self):
        """The routes other systems call. A module adds the routes it serves to them, such as its webhooks."""
        return API_PATH_PREFIXES

    @api.model
    def _request_path(self):
        if request:
            return request.httprequest.path
        # Odoo runs XML-RPC and JSON-RPC calls without the request, but the thread serving them keeps its URL.
        return urlsplit(getattr(threading.current_thread(), "url", "")).path

    @api.model
    def _log_event(self, action, note, document=None):
        """Record an action that changes no field, such as a call to another system, on its document when it is
        audited. Otherwise the note names the document."""
        if document and self.env[MODEL_AUDIT_MIXIN]._audit_is_audited(document._name):
            document._audit(action, note)
            return
        if document:
            note = f"{', '.join(document.sudo().mapped('display_name'))}: {note}"
        self.sudo().create({**self._origin_values(), "action": action, "note": note})

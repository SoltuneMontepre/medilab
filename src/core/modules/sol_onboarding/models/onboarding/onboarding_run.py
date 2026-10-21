from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_JOB_ITEM,
    MODEL_PERMISSION_MIXIN,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SECTOR,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.onboarding import (
    CRAWL_JOB,
    EVENT_RUN_ENDED,
    ITEMS_OPEN,
    RUN_DONE,
    RUN_DRAFT,
    RUN_ENDED,
    RUN_RUNNING,
)
from odoo.addons.sol_onboarding.services.adapters.registry import adapter_for


# Lượt Thu Thập
class OnboardingRun(models.Model):
    _name = MODEL_ONBOARDING_RUN
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Collection Run"
    _order = "id desc"
    _permission_actions = ("read", "create", "edit")

    _name_unique = models.Constraint("UNIQUE(name)", "A collection run reference is used once.")
    _one_running = models.UniqueIndex(
        "(state) WHERE state = 'running'", "Another collection run is running; start this one when it ends."
    )

    # Unique reference of the run, such as THU.2026.0001.
    name = fields.Char(string="Reference", required=True, readonly=True, copy=False, default="New")
    # The organisation whose accreditation scope the run collects.
    organisation_id = fields.Many2one(MODEL_ONBOARDING_ORGANISATION, string="Organisation", ondelete="restrict")
    # Sectors the run collects for.
    sector_ids = fields.Many2many(
        MODEL_ONBOARDING_SECTOR,
        "medilab_onboarding_run_sector_rel",
        "run_id",
        "sector_id",
        string="Sectors",
    )
    # draft, running, done, failed or cancelled.
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("running", "Running"),
            ("done", "Done"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        required=True,
        default=RUN_DRAFT,
        copy=False,
        index=True,
    )
    # The user who started the run and is notified when it ends.
    requested_by_id = fields.Many2one(
        "res.users", string="Requested By", required=True, default=lambda self: self.env.user, ondelete="restrict"
    )
    # Time the run started.
    started_at = fields.Datetime(string="Started At", copy=False)
    # Time the run ended.
    ended_at = fields.Datetime(string="Ended At", copy=False)
    # Pages the run fetched.
    page_count = fields.Integer(string="Pages Fetched", default=0, copy=False)
    # Pages the run skipped, for robots.txt, another host, the page limit or the content type.
    skipped_count = fields.Integer(string="Pages Skipped", default=0, copy=False)
    # Records the run staged.
    staged_count = fields.Integer(string="Records Staged", default=0, copy=False)
    # One line per page: fetched, skipped with its reason, or failed with its error.
    log = fields.Text(string="Log", copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(MODEL_ONBOARDING_RUN)
        return super().create(vals_list)

    def _crawl_items(self):
        return (
            self.env[MODEL_JOB_ITEM]
            .sudo()
            .search(
                [
                    ("job_id.key", "=", CRAWL_JOB),
                    ("document_model", "=", MODEL_ONBOARDING_RUN),
                    ("document_id", "in", self.ids),
                ]
            )
        )

    def action_start(self):
        self._check_permission("edit")
        sources = self.env[MODEL_ONBOARDING_SOURCE].sudo().search([("enabled", "=", True)])
        for run in self:
            if run.state != RUN_DRAFT:
                raise ValidationError(self.env._("Only a draft collection run can be started."))
            if not (run.organisation_id or run.sector_ids):
                raise ValidationError(self.env._("Choose an organisation or a sector to collect for."))
            if self.sudo().search_count([("state", "=", RUN_RUNNING)]):
                raise ValidationError(self.env._("Another collection run is running; start this one when it ends."))
            run.write({"state": RUN_RUNNING, "started_at": fields.Datetime.now(), "requested_by_id": self.env.user.id})
            # The index refuses a second running run that slipped past the check above.
            run.flush_recordset()
            for source in sources:
                run._queue_first_pages(source)
            if not run._crawl_items():
                run._finish(RUN_DONE)
        self.env.ref("sol_onboarding.ir_cron_onboarding_crawl").sudo()._trigger()

    def _queue_first_pages(self, source):
        adapter = adapter_for(source)
        if self.organisation_id.sudo().source_id == source:
            for url in adapter.organisation_pages(self.organisation_id):
                self._queue_page(source, url, None)
        for code in self.sector_ids.mapped("code"):
            if code in adapter.sectors:
                for url in adapter.sector_pages(code):
                    self._queue_page(source, url, code)

    def _queue_page(self, source, url: str, sector: str | None) -> bool:
        """Queue a page of the run for the crawl job. False when the source's page limit stops it."""
        self.ensure_one()
        source = source.sudo()
        key = f"{self.id}:{url}"
        on_host = self._crawl_items().filtered(
            lambda item: item.item_key.startswith(f"{self.id}:https://{source.host}/")
        )
        if key in on_host.mapped("item_key"):
            return True
        if len(on_host) >= source.page_limit:
            return False
        self.env[MODEL_SCHEDULED_JOB].queue(
            CRAWL_JOB, key, document=self, payload={"source_id": source.id, "sector": sector}
        )
        return True

    def action_cancel(self):
        self._check_permission("edit")
        for run in self:
            if run.state != RUN_RUNNING:
                raise ValidationError(self.env._("Only a running collection run can be cancelled."))
            run._crawl_items().filtered(lambda item: item.status == "pending").action_cancel()
            run._finish("cancelled")

    def action_refresh_organisations(self):
        """Start a refresh for each turned-on source that has none going, and run the job now."""
        self.ensure_one()
        self._check_permission("edit")
        jobs = self.env[MODEL_SCHEDULED_JOB]
        for source in self.env[MODEL_ONBOARDING_SOURCE].sudo().search([("enabled", "=", True)]):
            if not jobs._refresh_items(source, *ITEMS_OPEN):
                jobs._start_organisations_refresh(source)
        self.env.ref("sol_onboarding.ir_cron_onboarding_organisations").sudo()._trigger()

    def _finish(self, state):
        """End the run in this state and tell the person who started it."""
        self.ensure_one()
        if self.state in RUN_ENDED:
            return
        self.write({"state": state, "ended_at": fields.Datetime.now()})
        requester = self.requested_by_id
        localised = self.with_context(lang=requester.lang)
        labels = dict(localised._fields["state"]._description_selection(localised.env))
        body = localised.env._("Collection run %(name)s ended: %(state)s.", name=self.name, state=labels[state])
        self.env["mail.message"].raise_event(
            EVENT_RUN_ENDED,
            self,
            f"onboarding_run:{self.id}:ended",
            body,
            subject=self.name,
            partners=requester.partner_id,
        )

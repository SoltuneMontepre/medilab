from collections import Counter

from odoo import api, models

from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_SOURCE,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import (
    ITEM_DONE,
    ITEM_FAILED,
    ITEMS_OPEN,
    RUN_DONE,
    RUN_FAILED,
    RUN_RUNNING,
)
from odoo.addons.sol_onboarding.services.adapters.registry import adapter_for
from odoo.addons.sol_onboarding.services.fetcher import Fetcher, PageSkipped
from odoo.addons.sol_onboarding.services.parsing import pdf_text


# Lượt Thu Thập: crawling its pages and reporting when it ends.
class OnboardingRunCrawl(models.Model):
    _inherit = MODEL_ONBOARDING_RUN

    def _crawl_page(self, item):
        """Fetch the item's page, keep it, stage what it lists and queue the pages it links to."""
        # A batch claims its items at once; one cancelled since must not fetch.
        self.invalidate_recordset(["state"])
        if not self or self.state != RUN_RUNNING:
            return
        payload = item.payload
        source = self.env[MODEL_ONBOARDING_SOURCE].sudo().browse(payload["source_id"]).exists()
        if not source.enabled:
            raise PageSkipped(self.env._("source turned off"))
        fetched = Fetcher(source, f"run:{self.id}").fetch(item.item_key.partition(":")[2])
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(self, source, fetched)
        if fetched.content_type == "pdf" and not pdf_text(fetched.body):
            raise PageSkipped(self.env._("PDF without text"))
        parsed = adapter_for(source).parse(fetched, payload["sector"])
        # Transactions run at REPEATABLE READ: a cancel committed during the fetch makes the lock raise a serialization
        # error, and one not yet committed a LockError. The item is retried, which counts one attempt, and the retry
        # sees the cancel.
        self.lock_for_update(allow_referencing=True)
        self.invalidate_recordset(["state"])
        if self.state != RUN_RUNNING:
            return
        self.env[MODEL_ONBOARDING_STAGED_RECORD]._stage(snapshot, parsed.records)
        dropped = sum(not self._queue_page(source, link, payload["sector"]) for link in parsed.links)
        if dropped:
            item.payload = {**payload, "dropped": dropped}

    @api.model
    def _finish_settled(self):
        """End every running run with no page left to handle: failed when a page failed, done otherwise."""
        for run in self.search([("state", "=", RUN_RUNNING)]):
            statuses = set(run._crawl_items().mapped("status"))
            if not statuses & set(ITEMS_OPEN):
                run._finish(RUN_FAILED if ITEM_FAILED in statuses else RUN_DONE)

    def _report(self):
        """The counts and the log of the run, from its items and what it kept, in the context's language."""
        self.ensure_one()
        run = self.sudo()
        items = run._crawl_items().sorted("id")
        lines = []
        for item in items:
            address = item.item_key.partition(":")[2]
            if item.status == ITEM_FAILED:
                error = (item.last_error or "").strip()
                # A retried failure keeps its traceback, whose last line is the exception class and its message.
                if error.startswith("Traceback"):
                    error = error.rpartition("\n")[2].partition(": ")[2]
                lines.append(self.env._("failed %(address)s: %(error)s", address=address, error=error))
            elif "skipped" in item.payload:
                lines.append(
                    self.env._("skipped %(address)s: %(reason)s", address=address, reason=item.payload["skipped"])
                )
            elif item.status == ITEM_DONE:
                lines.append(self.env._("fetched %s", address))
            if dropped := item.payload.get("dropped"):
                lines.append(self.env._("%s pages not queued: page limit", dropped))
        kinds = Counter(run.staged_record_ids.mapped("kind"))
        labels = self.env[MODEL_ONBOARDING_STAGED_RECORD]._fields["kind"]._description_selection(self.env)
        lines += [f"{label}: {kinds[kind]}" for kind, label in labels if kinds[kind]]
        if not items:
            lines.append(self.env._("No turned-on source reads this organisation or these sectors."))
        return {
            "page_count": len(run.snapshot_ids),
            "skipped_count": len(items.filtered(lambda item: "skipped" in item.payload)),
            "staged_count": len(run.staged_record_ids),
            "log": "\n".join(lines),
        }

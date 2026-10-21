from dateutil.relativedelta import relativedelta
from lxml.etree import ParserError

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM, MODEL_SCHEDULED_JOB
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORGANISATION, MODEL_ONBOARDING_SOURCE
from odoo.addons.sol_onboarding.constants.onboarding import ORGANISATIONS_JOB
from odoo.addons.sol_onboarding.services.adapters.base import Parsed
from odoo.addons.sol_onboarding.services.adapters.registry import adapter_for
from odoo.addons.sol_onboarding.services.fetcher import Fetcher, PageSkipped, SourceBusy


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_onboarding_organisations(self):
        # A source starts a refresh when none of its pages are left and its last refresh began over half an interval
        # ago. The cron's schedule is the cadence; the half interval keeps a run by hand, which calls this every time,
        # from starting another, and lets the cron's next pass in even though the last refresh began after the cron.
        now = fields.Datetime.now()
        recent = now - (now + relativedelta(**{self.interval_type: self.interval_number}) - now) / 2
        for source in self.env[MODEL_ONBOARDING_SOURCE].sudo().search([("enabled", "=", True)]):
            refreshed_at = source.organisations_refreshed_at
            if self._refresh_items(source, "pending", "running") or (refreshed_at and refreshed_at > recent):
                continue
            if refreshed_at:
                # What the previous refresh did not see is no longer listed.
                self.env[MODEL_ONBOARDING_ORGANISATION].sudo().search(
                    [("source_id", "=", source.id), ("seen_at", "<", refreshed_at)]
                ).write({"active": False})
            source.organisations_refreshed_at = now
            stamp = fields.Datetime.to_string(now)
            for address in adapter_for(source).organisation_list_pages()[: source.page_limit]:
                self._queue_organisation_page(source, stamp, address)

    def _refresh_items(self, source, *statuses, stamp="%"):
        domain = [("item_key", "=like", f"organisations:{source.id}:{stamp}:%")]
        if statuses:
            domain.append(("status", "in", statuses))
        return self.env[MODEL_JOB_ITEM].sudo().search(domain)

    def _queue_organisation_page(self, source, stamp, address):
        self.queue(
            ORGANISATIONS_JOB,
            f"organisations:{source.id}:{stamp}:{address}",
            payload={"source_id": source.id, "stamp": stamp},
        )

    def _handle_onboarding_organisations(self, item):
        source = self.env[MODEL_ONBOARDING_SOURCE].sudo().browse(item.payload["source_id"]).exists()
        if not source or not source.enabled:
            return None
        stamp = item.payload["stamp"]
        address = item.item_key.removeprefix(f"organisations:{source.id}:{stamp}:")
        try:
            document = Fetcher(source, f"organisations:{stamp}").fetch(address)
        except SourceBusy as error:
            return error.until
        except PageSkipped as error:
            item.payload = {**item.payload, "skipped": str(error)}
            return None
        try:
            parsed = adapter_for(source).parse(document, None)
        except ParserError:
            # A page without content lists nothing.
            parsed = Parsed()
        self.env[MODEL_ONBOARDING_ORGANISATION]._upsert(source, parsed.organisations)
        queued = set(self._refresh_items(source, stamp=stamp).mapped("item_key"))
        for link in parsed.links:
            key = f"organisations:{source.id}:{stamp}:{link}"
            if key not in queued and len(queued) < source.page_limit:
                self._queue_organisation_page(source, stamp, link)
                queued.add(key)
        return None

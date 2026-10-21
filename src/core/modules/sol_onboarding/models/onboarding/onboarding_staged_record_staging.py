import hashlib
import json
from collections.abc import Iterable

from odoo import models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SECTOR, MODEL_ONBOARDING_STAGED_RECORD
from odoo.addons.sol_onboarding.constants.onboarding import (
    ACTION_CREATE,
    STAGED_ACCEPTED,
    STAGED_KEPT,
    STAGED_SUPERSEDED,
    STAGED_TO_REVIEW,
)
from odoo.addons.sol_onboarding.services.adapters.base import StagedValues
from odoo.addons.sol_onboarding.services.parsing import clean_text


# Bản Ghi Chờ Duyệt: what a fetched page stages, once per change at the source.
class OnboardingStagedRecordStaging(models.Model):
    _inherit = MODEL_ONBOARDING_STAGED_RECORD

    def _checksum(self, values: dict) -> str:
        text = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()

    def _stage(self, snapshot, values: Iterable[StagedValues]):
        """Stage the values read from the snapshot and return the records created.

        The same key and checksum as a kept record stages nothing; changed values stage a new record and supersede the
        older ones still to review. Runs as root, since the crawl job does."""
        staged = self.sudo()
        sectors = {sector.code: sector for sector in self.env[MODEL_ONBOARDING_SECTOR].sudo().search([])}
        created = {}
        for item in values:
            cleaned = {key: clean_text(value) for key, value in item.values.items()}
            checksum = self._checksum(cleaned)
            existing = staged.search(
                [
                    ("source_id", "=", snapshot.source_id.id),
                    ("kind", "=", item.kind),
                    ("external_key", "=", item.key),
                    ("state", "in", STAGED_KEPT),
                ]
            )
            if checksum in existing.mapped("checksum"):
                continue
            record = staged.create(
                {
                    "kind": item.kind,
                    "source_id": snapshot.source_id.id,
                    "run_id": snapshot.run_id.id,
                    "snapshot_id": snapshot.id,
                    "external_key": item.key,
                    "checksum": checksum,
                    "source_values": cleaned,
                    "lang": item.lang,
                    "sector_id": sectors[item.sector].id if item.sector else False,
                    "action": ACTION_CREATE,
                }
            )
            existing.filtered(lambda old: old.state == STAGED_TO_REVIEW).state = STAGED_SUPERSEDED
            created[record] = item.parent
        # Parents are resolved after the loop, since a page may list a child before its parent.
        for record, parent in created.items():
            if parent:
                record.parent_id = record._find_parent(*parent)
        return staged.browse([record.id for record in created])

    def _find_parent(self, kind, key):
        """The staged record of this kind and key from the same run, else the newest to review or accepted one of the
        source."""
        self.ensure_one()
        domain = [("kind", "=", kind), ("external_key", "=", key), ("source_id", "=", self.source_id.id)]
        in_run = self.search([*domain, ("run_id", "=", self.run_id.id)], limit=1)
        return in_run or self.search(
            [*domain, ("state", "in", (STAGED_TO_REVIEW, STAGED_ACCEPTED))], order="id desc", limit=1
        )

from odoo import models

from odoo.addons.sol_inventory.constants.jobs import EXPIRED, EXPIRING, STOCK_EXPIRY_JOB
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT, MODEL_STOCK_PACKAGE
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_inventory_stock_expiry(self):
        """Queue each lot and container that expired or expires soon, once for each."""
        expired_lots, expiring_lots = self.env[MODEL_STOCK_LOT]._to_warn()
        expired_containers, expiring_containers = self.env[MODEL_STOCK_PACKAGE]._to_warn()
        for kind, records, name in (
            (EXPIRED, expired_lots, "lot"),
            (EXPIRING, expiring_lots, "lot"),
            (EXPIRED, expired_containers, "container"),
            (EXPIRING, expiring_containers, "container"),
        ):
            for record in records:
                self.queue(STOCK_EXPIRY_JOB, f"{kind}:{name}:{record.id}", document=record, payload={"kind": kind})

    def _handle_inventory_stock_expiry(self, item):
        record = item._document()
        if record and record.exists():
            record._warn_expiry(item.payload["kind"])

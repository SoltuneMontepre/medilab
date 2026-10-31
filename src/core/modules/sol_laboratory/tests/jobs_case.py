from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase

from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM, MODEL_SCHEDULED_JOB

if TYPE_CHECKING:
    from odoo.orm.types import DomainType

JOB_KEY = "test.echo"
HANDLER = "_handle_test_echo"
FINDER = "_queue_test_echo"
JOB_LOGGER = "odoo.addons.sol_laboratory.models.system.scheduled_job"


class JobsCase(TransactionCase):
    """A job with the key test.echo whose handler the test chooses, and the items it was given."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.job = cls.env[MODEL_SCHEDULED_JOB].create({"key": JOB_KEY, "name": "Echo", "retry_delay_minutes": 5})

    def handle_with(self, handler):
        patcher = patch.object(type(self.env[MODEL_SCHEDULED_JOB]), HANDLER, handler, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def find_with(self, finder):
        patcher = patch.object(type(self.env[MODEL_SCHEDULED_JOB]), FINDER, finder, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record_handler(self):
        handled = []

        def handler(job, item):
            handled.append(item.item_key)

        self.handle_with(handler)
        return handled

    def queue(self, item_key, payload=None, document=None):
        return self.env[MODEL_SCHEDULED_JOB].queue(JOB_KEY, item_key, document=document, payload=payload)

    def run_pass(self):
        # The cron opens its own cursor; registry test mode makes it share the test's connection.
        with self.registry_test_mode():
            self.job.cron_id.method_direct_trigger()
        self.env.invalidate_all()

    def items(self, status=None):
        domain: DomainType = [("job_id", "=", self.job.id)]
        if status:
            domain.append(("status", "=", status))
        return self.env[MODEL_JOB_ITEM].search(domain, order="id")

    @staticmethod
    def minutes_ago(minutes):
        return fields.Datetime.now() - timedelta(minutes=minutes)

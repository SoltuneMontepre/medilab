import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo import fields
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.services import fetcher

MAX_PASSES = 50
NOT_FOUND = (404, "text/html", b"", {})


# Base of the Onboarding tests: a turned-on source, a frozen clock that sleeping moves forward, and a network that
# answers only from the pages a test serves.
class OnboardingCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # CI installs the demo data: its running run would refuse every start, and its organisations would be suggested.
        cls.env[MODEL_ONBOARDING_RUN].search([("state", "=", "running")]).write({"state": "cancelled"})
        cls.env[MODEL_ONBOARDING_ORGANISATION].search([]).write({"active": False})
        # The shipped sources would otherwise join every run and refresh.
        cls.env[MODEL_ONBOARDING_SOURCE].sudo().search([]).enabled = False
        cls.source = (
            cls.env[MODEL_ONBOARDING_SOURCE]
            .sudo()
            .create(
                {
                    "name": "Lab",
                    "adapter": "pages",
                    "host": "lab.example",
                    "start_url": "https://lab.example/",
                    "delay_seconds": 2,
                    "page_limit": 5,
                    "enabled": True,
                }
            )
        )
        cls.admin = new_test_user(cls.env, login="onboarding_admin", groups=f"base.group_user,{ADMINISTRATOR_GROUP}")
        cls.reader = new_test_user(
            cls.env,
            login="onboarding_reader",
            groups=(
                "base.group_user,sol_laboratory.group_permission_onboarding_run_read_all,"
                "sol_laboratory.group_permission_onboarding_staged_record_read_all"
            ),
        )

    def setUp(self):
        super().setUp()
        self.addCleanup(fetcher.ROBOTS.clear)
        self.addCleanup(fetcher.LAST_REQUESTS.clear)
        self.addCleanup(fetcher.UNAVAILABLE.clear)
        frozen = freeze_time("2026-10-21 08:00:00")
        self.clock = frozen.start()
        self.addCleanup(frozen.stop)
        self.sleeps = []
        self.startPatcher(patch.object(fetcher, "sleep", side_effect=self._sleep))
        self.calls = self.serve({})

    def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock.tick(seconds)

    def serve(self, pages):
        """Answer requests.Session.get from pages, mapping an address to (status, content type, body, headers) or to an
        exception to raise; other addresses answer 404. Returns the calls, in order."""
        calls = []

        def get(session, url, **kwargs):
            calls.append(
                SimpleNamespace(
                    url=url,
                    kwargs=kwargs,
                    time=datetime.now(),
                    headers={**session.headers, **(kwargs.get("headers") or {})},
                    trust_env=session.trust_env,
                    verify=kwargs.get("verify", session.verify),
                )
            )
            page = pages.get(url, NOT_FOUND)
            if isinstance(page, Exception):
                raise page
            status, content_type, body, headers = page
            response = requests.Response()
            response.status_code = status
            response.url = url
            response.headers.update({"Content-Type": content_type, **headers})
            response.raw = io.BytesIO(body)
            return response

        self.startPatcher(patch.object(requests.Session, "get", get))
        return calls

    def run_until_settled(self, job_key):
        """Run batches of the job while due items remain, then once more so its finder sees what settled."""
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(job_key)
        for _ in range(MAX_PASSES):
            job._run_batch()
            if not job._due_count(fields.Datetime.now()):
                break
        else:
            self.fail(f"Job {job_key} still has due items after {MAX_PASSES} passes")
        job._run_batch()

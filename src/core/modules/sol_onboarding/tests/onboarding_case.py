import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo.tests import TransactionCase, new_test_user

from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE
from odoo.addons.sol_onboarding.services import fetcher

NOT_FOUND = (404, "text/html", b"", {})


# Base of the Onboarding tests: a turned-on source, a frozen clock that sleeping moves forward, and a network that
# answers only from the pages a test serves.
class OnboardingCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        cls.reader = new_test_user(cls.env, login="onboarding_reader", groups="base.group_user")

    def setUp(self):
        super().setUp()
        self.addCleanup(fetcher.ROBOTS.clear)
        self.addCleanup(fetcher.LAST_REQUESTS.clear)
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

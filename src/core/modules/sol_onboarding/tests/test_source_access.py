from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE

SOURCE_VALUES = {
    "name": "Test source",
    "adapter": "test",
    "host": "lab.example",
    "start_url": "https://lab.example/start",
}


@tagged("post_install", "-at_install")
class TestSourceAccess(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, login="onboarding_admin", groups=f"base.group_user,{ADMINISTRATOR_GROUP}")
        cls.sources = cls.env[MODEL_ONBOARDING_SOURCE].sudo()

    def test_administrator_cannot_read_sources_through_the_orm(self):
        with self.assertRaises(AccessError):
            self.env[MODEL_ONBOARDING_SOURCE].with_user(self.admin).search_read([], ["name"])

    @mute_logger("odoo.http")
    def test_administrator_cannot_read_sources_through_the_api(self):
        self.authenticate(self.admin.login, self.admin.login)

        with self.assertRaisesRegex(JsonRpcException, "AccessError"):
            self.make_jsonrpc_request(
                "/web/dataset/call_kw",
                {
                    "model": MODEL_ONBOARDING_SOURCE,
                    "method": "search_read",
                    "args": [[]],
                    "kwargs": {"fields": ["name"]},
                },
            )

    def test_nothing_shows_sources(self):
        for model, field in (
            ("ir.ui.view", "model"),
            ("ir.actions.act_window", "res_model"),
            ("ir.access", "model_id.model"),
        ):
            self.assertFalse(self.env[model].sudo().search_count([(field, "=", MODEL_ONBOARDING_SOURCE)]), model)

    def test_a_source_is_off_by_default(self):
        source = self.sources.create(SOURCE_VALUES)
        self.assertEqual(
            (source.enabled, source.active, source.delay_seconds, source.page_limit), (False, True, 2, 500)
        )

    def test_a_start_address_must_be_https_on_the_host(self):
        for start_url in (
            "http://lab.example/",
            "https://other.example/",
            "https://lab.example:abc/",
            "https://[bad/",
            "https://user@lab.example/",
            "https://lab.example:8443/",
        ):
            with self.subTest(start_url=start_url), self.assertRaises(ValidationError):
                self.sources.create({**SOURCE_VALUES, "start_url": start_url})

    def test_the_delay_and_the_page_limit_stay_in_range(self):
        for values in ({"delay_seconds": -1}, {"page_limit": 0}):
            with self.subTest(values=values), self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
                self.sources.create({**SOURCE_VALUES, **values})

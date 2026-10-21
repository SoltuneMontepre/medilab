from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SECTOR,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.onboarding import CRAWL_JOB
from odoo.addons.sol_onboarding.services.adapters.base import OrganisationValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

ORGANISATION_PAGE = "https://lab.example/org/a"
FOOD_PAGE = "https://lab.example/food"


@tagged("post_install", "-at_install")
class TestRuns(OnboardingCase):
    def setUp(self):
        super().setUp()
        self.runs = self.env[MODEL_ONBOARDING_RUN]
        self.food = self.env[MODEL_ONBOARDING_SECTOR].search([("code", "=", "food")])
        self.organisation = self.env[MODEL_ONBOARDING_ORGANISATION]._upsert(
            self.source, [OrganisationValues(key="a", name="Lab A", url=ORGANISATION_PAGE)]
        )

    def run_of(self, **values):
        return self.runs.with_user(self.admin).create({"requested_by_id": self.admin.id, **values})

    def items(self, run):
        return (
            self.env[MODEL_JOB_ITEM]
            .sudo()
            .search([("document_model", "=", MODEL_ONBOARDING_RUN), ("document_id", "=", run.id)])
        )

    def test_a_run_gets_a_yearly_reference(self):
        self.assertRegex(self.run_of(sector_ids=self.food).name, r"^THU\.\d{4}\.\d{4}$")

    def test_starting_queues_the_first_pages_of_each_turned_on_source(self):
        off = (
            self.env[MODEL_ONBOARDING_SOURCE]
            .sudo()
            .create(
                {
                    "name": "Off",
                    "adapter": "pages",
                    "host": "off.example",
                    "start_url": "https://off.example/",
                    "enabled": False,
                }
            )
        )
        stranger = self.env[MODEL_ONBOARDING_ORGANISATION]._upsert(
            off, [OrganisationValues(key="z", name="Lab Z", url="https://off.example/org/z")]
        )
        run = self.run_of(organisation_id=self.organisation.id, sector_ids=self.food)
        run.action_start()
        items = self.items(run)
        self.assertEqual(
            {item.item_key: item.payload for item in items},
            {
                f"{run.id}:{ORGANISATION_PAGE}": {"source_id": self.source.id, "sector": None},
                f"{run.id}:{FOOD_PAGE}": {"source_id": self.source.id, "sector": "food"},
            },
        )
        self.assertEqual(items.job_id.key, CRAWL_JOB)
        self.assertEqual((run.state, run.requested_by_id), ("running", self.admin))
        self.assertTrue(run.started_at)
        run.action_cancel()
        other = self.run_of(organisation_id=stranger.id, sector_ids=self.food)
        other.action_start()
        self.assertEqual(self.items(other).mapped("item_key"), [f"{other.id}:{FOOD_PAGE}"])

    def test_a_run_needs_an_organisation_or_a_sector(self):
        with self.assertRaises(ValidationError):
            self.run_of().action_start()

    def test_starting_a_second_run_is_refused_with_a_message(self):
        first = self.run_of(sector_ids=self.food)
        second = self.run_of(sector_ids=self.food)
        first.action_start()
        with self.assertRaisesRegex(ValidationError, "Another collection run is running"):
            second.action_start()
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            second.write({"state": "running"})
            second.flush_recordset()

    def test_a_run_that_queues_nothing_ends_at_once(self):
        cosmetics = self.env[MODEL_ONBOARDING_SECTOR].search([("code", "=", "cosmetics")])
        empty = self.run_of(sector_ids=cosmetics)
        empty.action_start()
        self.assertEqual(empty.state, "done")
        self.assertTrue(empty.ended_at)
        self.run_of(sector_ids=self.food).action_start()

    def test_cancelling_cancels_pending_items(self):
        run = self.run_of(sector_ids=self.food)
        run.action_start()
        run.action_cancel()
        self.assertEqual(run.state, "cancelled")
        self.assertTrue(run.ended_at)
        self.assertEqual(self.items(run).mapped("status"), ["cancelled"])

    def test_a_run_stops_queueing_pages_at_the_source_limit(self):
        self.source.page_limit = 2
        run = self.run_of(sector_ids=self.food)
        results = [run._queue_page(self.source, f"https://lab.example/p{n}", None) for n in range(3)]
        self.assertEqual(results, [True, True, False])
        self.assertTrue(run._queue_page(self.source, "https://lab.example/p0", None))
        self.assertEqual(len(self.items(run)), 2)

    def test_the_starter_is_notified_when_the_run_ends(self):
        self.admin.notification_type = "inbox"
        run = self.run_of(sector_ids=self.food)
        run.action_start()
        run._finish("done")
        message = self.env["mail.message"].search([("notification_key", "=", f"onboarding_run:{run.id}:ended")])
        self.assertEqual(len(message), 1)
        self.assertIn(self.admin.partner_id, message.notified_partner_ids)
        self.assertEqual(run.state, "done")
        run._finish("failed")
        self.assertEqual(run.state, "done")

    def test_only_permission_holders_start_runs(self):
        run = self.run_of(sector_ids=self.food)
        with self.assertRaises(AccessError):
            run.with_user(self.reader).action_start()
        with self.assertRaises(AccessError):
            run.with_user(self.reader).action_cancel()

    def test_refresh_by_hand_triggers_the_job(self):
        run = self.run_of(sector_ids=self.food)
        cron = self.env.ref("sol_onboarding.ir_cron_onboarding_organisations")
        with patch.object(type(cron), "_trigger") as trigger:
            run.with_user(self.admin).action_refresh_organisations()
            trigger.assert_called_once()
            self.assertTrue(
                self.env[MODEL_JOB_ITEM].sudo().search([("item_key", "=like", f"organisations:{self.source.id}:%")])
            )
            with self.assertRaises(AccessError):
                run.with_user(self.reader).action_refresh_organisations()

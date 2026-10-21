from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tools import file_open, mute_logger

from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_RUN, MODEL_ONBOARDING_SECTOR
from odoo.addons.sol_onboarding.constants.onboarding import CRAWL_JOB
from odoo.addons.sol_onboarding.services.fetcher import Fetcher, SourceBusy
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

FOOD = "https://lab.example/food"
SECOND = "https://lab.example/food/2"
COSMETICS = "https://lab.example/cosmetics"
ELSEWHERE = "https://other.example/food"
ROBOTS = "https://lab.example/robots.txt"
# The laboratory job logs an item that failed its last attempt.
JOB_LOGGER = "odoo.addons.sol_laboratory.models.system.scheduled_job"
RUN_REPORT = ["ended_at", "page_count", "skipped_count", "staged_count", "log"]


def page(*items, links=()):
    rows = "".join(f"<li {item}></li>" for item in items)
    anchors = "".join(f'<a rel="next" href="{link}">next</a>' for link in links)
    return 200, "text/html", f"<html><body><ul>{rows}</ul>{anchors}</body></html>".encode(), {}


def method(code):
    return f'data-kind="testing_method" data-key="{code}" data-code="{code}" data-name="M {code}" data-field-key="chem"'


def sample_type(name):
    return f'data-kind="sample_type" data-key="{name}" data-name="{name}"'


@tagged("post_install", "-at_install")
class TestCrawl(OnboardingCase):
    def setUp(self):
        super().setUp()
        self.job = self.env[MODEL_SCHEDULED_JOB]._by_key(CRAWL_JOB)
        self.food = self.env[MODEL_ONBOARDING_SECTOR].search([("code", "=", "food")])

    def start(self):
        run = self.env[MODEL_ONBOARDING_RUN].with_user(self.admin).create({"sector_ids": self.food.ids})
        run.action_start()
        return run.sudo()

    def crawl(self):
        run = self.start()
        self.run_until_settled(CRAWL_JOB)
        return run

    def staged(self, run):
        return sorted(run.staged_record_ids.mapped(lambda record: (record.external_key, record.state)))

    def test_a_run_for_food_stages_only_what_is_listed_for_food(self):
        calls = self.serve(
            {
                FOOD: page(method("TCVN 1"), links=[SECOND]),
                SECOND: page(method("TCVN 2")),
                COSMETICS: page(method("TCVN 9")),
            }
        )
        run = self.crawl()

        self.assertEqual(self.staged(run), [("TCVN 1", "to_review"), ("TCVN 2", "to_review")])
        self.assertEqual(run.staged_record_ids.sector_id, self.food)
        self.assertEqual([call.url for call in calls if call.url != ROBOTS], [FOOD, SECOND])
        self.assertEqual(run.state, "done")

    def test_running_twice_on_unchanged_sources_stages_nothing_the_second_time(self):
        self.serve(
            {FOOD: page(method("TCVN 1"), sample_type("Nước mặt"), links=[SECOND]), SECOND: page(method("TCVN 2"))}
        )
        first = self.crawl()
        second = self.crawl()

        self.assertEqual(first.staged_count, 3)
        self.assertEqual((second.state, second.page_count, second.staged_count), ("done", 2, 0))
        self.assertFalse(second.staged_record_ids)

    @mute_logger(JOB_LOGGER)
    def test_a_page_failing_every_attempt_fails_the_run_and_keeps_what_was_staged(self):
        self.job.retry_delay_minutes = 0
        self.serve({FOOD: page(method("TCVN 1"), links=[SECOND]), SECOND: (503, "text/html", b"", {})})
        run = self.crawl()

        failed = run._crawl_items().filtered(lambda item: item.status == "failed")
        self.assertEqual((failed.item_key, failed.attempts), (f"{run.id}:{SECOND}", 3))
        self.assertEqual(run.state, "failed")
        # A retried failure keeps its traceback; the log gives its last line.
        error = "odoo.addons.sol_onboarding.services.fetcher.PageUnavailable: The source answered 503."
        self.assertIn(f"failed {SECOND}: {error}", run.log.splitlines())
        self.assertEqual(self.staged(run), [("TCVN 1", "to_review")])

    @mute_logger(JOB_LOGGER)
    def test_a_4xx_page_fails_at_once(self):
        run = self.crawl()

        item = run._crawl_items()
        self.assertEqual((item.status, item.attempts), ("failed", 1))
        self.assertEqual(run.state, "failed")
        self.assertEqual(run.log, f"failed {FOOD}: The source answered 404.")

    def test_a_run_stops_at_the_page_limit(self):
        links = [f"{FOOD}/{number}" for number in range(1, 9)]
        self.serve({FOOD: page(links=links), **{link: page() for link in links}})
        run = self.crawl()

        self.assertEqual((len(run.snapshot_ids), run.page_count), (5, 5))
        self.assertIn("4 pages not queued: page limit", run.log.splitlines())

    def test_skipped_pages_are_counted_and_named(self):
        private, data = "https://lab.example/private/a", "https://lab.example/data.csv"
        self.serve(
            {
                ROBOTS: (200, "text/plain", b"User-agent: *\nDisallow: /private\n", {}),
                FOOD: page(links=[private, ELSEWHERE, data]),
                data: (200, "text/csv", b"a,b", {}),
            }
        )
        run = self.crawl()

        self.assertEqual((run.state, run.page_count, run.skipped_count), ("done", 1, 3))
        self.assertEqual(
            run.log.splitlines(),
            [
                f"fetched {FOOD}",
                f"skipped {private}: disallowed by robots.txt",
                f"skipped {ELSEWHERE}: another host",
                f"skipped {data}: content type text/csv not accepted",
            ],
        )

    def test_a_cancelled_run_fetches_no_more_pages_and_keeps_what_it_staged(self):
        calls = self.serve({FOOD: page(method("TCVN 1"), links=[SECOND]), SECOND: page(method("TCVN 2"))})
        run = self.start()
        self.job._run_batch()
        run.with_user(self.admin).action_cancel()
        self.run_until_settled(CRAWL_JOB)

        self.assertNotIn(SECOND, [call.url for call in calls])
        self.assertEqual(run.state, "cancelled")
        self.assertEqual(self.staged(run), [("TCVN 1", "to_review")])

    def test_cancelled_run_stages_nothing_more(self):
        calls = self.serve({FOOD: page(method("TCVN 1"), links=[SECOND])})
        run = self.start()
        item = self.job._claim(fields.Datetime.now())
        run.with_user(self.admin).action_cancel()
        report = run.read(RUN_REPORT)
        self.clock.tick(timedelta(minutes=1))

        self.assertIsNone(self.job._handle_onboarding_crawl(item))
        self.run_until_settled(CRAWL_JOB)

        self.assertEqual(calls, [])
        self.assertFalse(run.staged_record_ids)
        self.assertEqual(run.read(RUN_REPORT), report)

    def test_a_run_cancelled_during_a_fetch_stages_and_queues_nothing(self):
        self.serve({FOOD: page(method("TCVN 1"), links=[SECOND])})
        run = self.start()
        fetch = Fetcher.fetch

        def fetch_then_cancel(fetcher, url):
            fetched = fetch(fetcher, url)
            run.with_user(self.admin).action_cancel()
            return fetched

        with patch.object(Fetcher, "fetch", fetch_then_cancel):
            self.run_until_settled(CRAWL_JOB)

        self.assertEqual((run.state, run.page_count), ("cancelled", 0))
        self.assertFalse(run.staged_record_ids)
        self.assertEqual(run._crawl_items().mapped("item_key"), [f"{run.id}:{FOOD}"])

    def test_counts_and_log_are_written_when_the_run_ends(self):
        self.serve(
            {
                FOOD: page(method("TCVN 1"), method("TCVN 2"), sample_type("Nước mặt"), links=[SECOND, ELSEWHERE]),
                SECOND: page(method("TCVN 3")),
            }
        )
        run = self.crawl()

        self.assertEqual((run.page_count, run.skipped_count, run.staged_count), (2, 1, 4))
        self.assertEqual(
            run.log.splitlines(),
            [
                f"fetched {FOOD}",
                f"fetched {SECOND}",
                f"skipped {ELSEWHERE}: another host",
                "Testing Method: 3",
                "Sample Type: 1",
            ],
        )

    def test_a_pdf_without_text_is_skipped_with_a_log_line(self):
        scan = "https://lab.example/scan.pdf"
        with file_open("sol_onboarding/tests/pages/scanned.pdf", "rb") as scanned:
            self.serve({FOOD: page(links=[scan]), scan: (200, "application/pdf", scanned.read(), {})})
        run = self.crawl()

        self.assertEqual((run.page_count, run.skipped_count), (2, 1))
        self.assertIn(f"skipped {scan}: PDF without text", run.log.splitlines())

    def test_a_busy_source_defers_the_page_without_an_attempt(self):
        run = self.start()
        until = fields.Datetime.now() + timedelta(minutes=5)
        with patch.object(Fetcher, "fetch", side_effect=SourceBusy(until)):
            self.job._run_batch()

        item = run._crawl_items()
        self.assertEqual((item.status, item.attempts, item.next_attempt_at), ("pending", 0, until))
        self.assertEqual(run.state, "running")

    def test_a_turned_off_source_is_not_fetched(self):
        run = self.start()
        self.source.enabled = False
        self.run_until_settled(CRAWL_JOB)

        self.assertEqual(self.calls, [])
        self.assertEqual(run.log, f"skipped {FOOD}: source turned off")

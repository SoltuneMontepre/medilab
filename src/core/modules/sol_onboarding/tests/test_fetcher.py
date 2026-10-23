from datetime import timedelta
from itertools import count, pairwise
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import LockError
from odoo.tests import tagged

from .onboarding_case import OnboardingCase
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE
from odoo.addons.sol_onboarding.constants.onboarding import CONNECT_TIMEOUT_SECONDS, MAX_BYTES, TIMEOUT_SECONDS
from odoo.addons.sol_onboarding.services import fetcher as fetcher_module
from odoo.addons.sol_onboarding.services.fetcher import (
    Fetcher,
    PageRefused,
    PageSkipped,
    PageUnavailable,
    SourceBusy,
)

ROBOTS_URL = "https://lab.example/robots.txt"
HTML = (200, "text/html", b"<p>Page</p>", {})
# Redirect targets that look like the source's host, with the reason each is refused.
REDIRECT_REFUSALS = {
    "https://evil.test/": "redirect off the host",
    "https://lab.example.evil.test/": "redirect off the host",
    "https://lab.example@evil.test/": "redirect off the host",
    "https://lab.example:8443/": "redirect off the host",
    "http://lab.example/": "not HTTPS",
}


def redirect(location):
    return (302, "text/html", b"", {"Location": location})


def pages_of(calls):
    return [call.url for call in calls if call.url != ROBOTS_URL]


@tagged("post_install", "-at_install")
class TestFetcher(OnboardingCase):
    def assertDelayKept(self, calls):
        for earlier, later in pairwise(calls):
            self.assertGreaterEqual((later.time - earlier.time).total_seconds(), self.source.delay_seconds)

    def test_fetches_a_page_on_the_source_host(self):
        self.serve({"https://lab.example/a": HTML})

        page = Fetcher(self.source, "run:1").fetch("https://lab.example/a")

        self.assertEqual((page.url, page.content_type, page.body), ("https://lab.example/a", "html", b"<p>Page</p>"))
        self.assertEqual(page.fetched_at, fields.Datetime.now())

    def test_refuses_another_host(self):
        calls = self.serve({"https://evil.test/": HTML})

        with self.assertRaisesRegex(PageSkipped, "another host"):
            Fetcher(self.source, "run:1").fetch("https://evil.test/")
        self.assertEqual(calls, [])

    def test_refuses_look_alike_addresses(self):
        for url in (
            "https://lab.example.evil.test/",
            "https://lab.example@evil.test/",
            "https://lab.example:8443/",
            "http://lab.example/",
        ):
            with self.subTest(url=url), self.assertRaises(PageSkipped):
                Fetcher(self.source, "run:1").fetch(url)
        self.assertEqual(self.calls, [])

    def test_checks_every_redirect(self):
        moves = {f"https://lab.example/move/{index}": target for index, target in enumerate(REDIRECT_REFUSALS)}
        hops = {f"https://lab.example/hop{index}": redirect(f"/hop{index + 1}") for index in range(6)}
        calls = self.serve(
            {
                **{url: redirect(target) for url, target in moves.items()},
                "https://lab.example/moved": redirect("https://lab.example/b"),
                "https://lab.example/b": HTML,
                **hops,
                "https://lab.example/hop6": HTML,
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        for url, target in moves.items():
            with self.subTest(target=target), self.assertRaisesRegex(PageSkipped, REDIRECT_REFUSALS[target]):
                fetcher.fetch(url)
        self.assertEqual(pages_of(calls), list(moves))

        self.assertEqual(fetcher.fetch("https://lab.example/moved").url, "https://lab.example/b")
        self.assertEqual(fetcher.fetch("https://lab.example/hop1").url, "https://lab.example/hop6")
        with self.assertRaisesRegex(PageSkipped, "too many redirects"):
            fetcher.fetch("https://lab.example/hop0")
        self.assertEqual(pages_of(calls)[-6:], [f"https://lab.example/hop{index}" for index in range(6)])
        self.assertDelayKept(calls)

    def test_follows_robots_txt(self):
        calls = self.serve(
            {
                ROBOTS_URL: (200, "text/plain", b"User-agent: *\nDisallow: /private\n", {}),
                "https://lab.example/private": HTML,
                "https://lab.example/public": HTML,
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        with self.assertRaisesRegex(PageSkipped, "robots.txt"):
            fetcher.fetch("https://lab.example/private")
        fetcher.fetch("https://lab.example/public")
        Fetcher(self.source, "run:1").fetch("https://lab.example/public")
        self.assertEqual(
            [call.url for call in calls], [ROBOTS_URL, "https://lab.example/public", "https://lab.example/public"]
        )

        calls = self.serve({"https://lab.example/private": HTML})
        Fetcher(self.source, "run:2").fetch("https://lab.example/private")
        self.assertEqual([call.url for call in calls], [ROBOTS_URL, "https://lab.example/private"])

        self.serve({ROBOTS_URL: (503, "text/plain", b"", {}), "https://lab.example/public": HTML})
        with self.assertRaises(PageUnavailable):
            Fetcher(self.source, "run:3").fetch("https://lab.example/public")

    def test_reads_an_unusable_robots_txt_as_allowing_all(self):
        calls = self.serve(
            {
                ROBOTS_URL: (200, "text/html", b"<p>Not found</p>", {}),
                "https://lab.example/a": HTML,
                "https://lab.example/b": HTML,
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        fetcher.fetch("https://lab.example/a")
        fetcher.fetch("https://lab.example/b")

        self.assertEqual([call.url for call in calls], [ROBOTS_URL, "https://lab.example/a", "https://lab.example/b"])

    def test_a_robots_txt_redirected_off_the_host_or_too_often_disallows_every_page(self):
        hops = {f"https://lab.example/robots/{index}": redirect(f"/robots/{index + 1}") for index in range(6)}
        for robots, key in ((redirect("https://evil.test/robots.txt"), "run:1"), (redirect("/robots/0"), "run:2")):
            with self.subTest(run=key):
                calls = self.serve({ROBOTS_URL: robots, **hops, "https://lab.example/a": HTML})
                with self.assertRaisesRegex(PageSkipped, "disallowed by robots.txt"):
                    Fetcher(self.source, key).fetch("https://lab.example/a")
                self.assertNotIn("https://lab.example/a", [call.url for call in calls])

    def test_keeps_the_delay_between_requests(self):
        self.calls = self.serve(
            {"https://lab.example/a": HTML, "https://lab.example/b": HTML, "https://lab.example/c": HTML}
        )
        fetcher = Fetcher(self.source, "run:1")
        fetcher.fetch("https://lab.example/a")
        fetcher.fetch("https://lab.example/b")
        times = [call.time for call in self.calls if not call.url.endswith("/robots.txt")]
        self.assertGreaterEqual((times[1] - times[0]).total_seconds(), 2)

        self.clock.tick(1.5)
        fetcher.fetch("https://lab.example/c")
        self.assertEqual(self.sleeps, [2, 2, 0.5])

    def test_keeps_the_delay_across_fetchers(self):
        calls = self.serve({"https://lab.example/a": HTML, "https://lab.example/b": HTML})

        Fetcher(self.source, "run:1").fetch("https://lab.example/a")
        # Another worker shares only the database with this one.
        fetcher_module.ROBOTS.clear()
        fetcher_module.LAST_REQUESTS.clear()
        self.env.invalidate_all()
        Fetcher(self.env[MODEL_ONBOARDING_SOURCE].sudo().browse(self.source.id), "run:1").fetch("https://lab.example/b")

        self.assertEqual(
            [call.url for call in calls], [ROBOTS_URL, "https://lab.example/a", ROBOTS_URL, "https://lab.example/b"]
        )
        self.assertDelayKept(calls)

    def test_defers_while_another_worker_holds_the_source(self):
        calls = self.serve({"https://lab.example/a": HTML})
        locked = LockError("Cannot grab a lock on records")

        with (
            patch.object(self.registry[MODEL_ONBOARDING_SOURCE], "lock_for_update", side_effect=locked),
            self.assertRaises(SourceBusy) as busy,
        ):
            Fetcher(self.source, "run:1").fetch("https://lab.example/a")

        self.assertEqual(busy.exception.until, fields.Datetime.now() + timedelta(seconds=2))
        self.assertEqual(calls, [])

    def test_sends_get_without_cookies_or_credentials(self):
        calls = self.serve({"https://lab.example/a": HTML})

        Fetcher(self.source, "run:1").fetch("https://lab.example/a")

        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn("MediLab", call.headers["User-Agent"])
            self.assertEqual(set(call.headers), {"User-Agent"})
            self.assertEqual(
                call.kwargs,
                {"stream": True, "allow_redirects": False, "timeout": (CONNECT_TIMEOUT_SECONDS, TIMEOUT_SECONDS)},
            )
            self.assertIsNot(call.verify, False)
            self.assertFalse(call.trust_env)

    def test_stops_reading_at_ten_megabytes(self):
        self.serve(
            {
                "https://lab.example/chunked": (200, "text/html", b"x" * (11 * 1024 * 1024), {}),
                # Its body is small, so only the announced length can skip it.
                "https://lab.example/announced": (200, "text/html", b"x", {"Content-Length": str(20 * 1024 * 1024)}),
                "https://lab.example/full": (200, "text/html", b"x" * MAX_BYTES, {}),
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        for url in ("https://lab.example/chunked", "https://lab.example/announced"):
            with self.subTest(url=url), self.assertRaisesRegex(PageSkipped, "over 10 MB"):
                fetcher.fetch(url)
        self.assertEqual(len(fetcher.fetch("https://lab.example/full").body), MAX_BYTES)

    def test_stops_at_thirty_seconds(self):
        calls = self.serve(
            {
                "https://lab.example/silent": requests.Timeout(),
                "https://lab.example/slow": (200, "text/html", b"x" * 1024 * 1024, {}),
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        with self.assertRaises(PageUnavailable):
            fetcher.fetch("https://lab.example/silent")
        self.assertEqual(calls[-1].kwargs["timeout"], (CONNECT_TIMEOUT_SECONDS, TIMEOUT_SECONDS))
        # Each read of the stream ends 20 seconds after the previous one.
        with patch.object(fetcher_module, "monotonic", side_effect=count(0, 20)), self.assertRaises(PageUnavailable):
            fetcher.fetch("https://lab.example/slow")

    def test_accepts_html_pdf_and_json_only(self):
        self.serve(
            {
                "https://lab.example/page": (200, "text/html; charset=utf-8", b"<p>Page</p>", {}),
                "https://lab.example/scope.pdf": (200, "application/pdf", b"%PDF-1.7", {}),
                "https://lab.example/list.json": (200, "application/json", b"[]", {}),
                "https://lab.example/logo.png": (200, "image/png", b"\x89PNG", {}),
                "https://lab.example/notes.txt": (200, "text/plain", b"Notes", {}),
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        self.assertEqual(
            [fetcher.fetch(f"https://lab.example/{path}").content_type for path in ("page", "scope.pdf", "list.json")],
            ["html", "pdf", "json"],
        )
        for path in ("logo.png", "notes.txt"):
            with self.subTest(path=path), self.assertRaisesRegex(PageSkipped, "not accepted"):
                fetcher.fetch(f"https://lab.example/{path}")

    def test_maps_answers(self):
        calls = self.serve(
            {
                "https://lab.example/gone": (404, "text/html", b"", {}),
                "https://lab.example/busy": (503, "text/html", b"", {}),
                "https://lab.example/down": requests.ConnectionError(),
            }
        )
        fetcher = Fetcher(self.source, "run:1")

        with self.assertRaises(PageRefused) as refused:
            fetcher.fetch("https://lab.example/gone")
        self.assertIsInstance(refused.exception, PermanentJobError)
        for path in ("busy", "down"):
            with self.subTest(path=path), self.assertRaises(PageUnavailable) as unavailable:
                fetcher.fetch(f"https://lab.example/{path}")
            self.assertNotIsInstance(unavailable.exception, PermanentJobError)
        # assertRaises rolls each failed fetch back to a savepoint, as the job does, and the next request still waits.
        self.assertDelayKept(calls)

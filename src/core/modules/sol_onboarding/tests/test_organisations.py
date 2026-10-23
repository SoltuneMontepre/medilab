from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORGANISATION
from odoo.addons.sol_onboarding.constants.onboarding import ORGANISATIONS_JOB, SUGGEST_CONTEXT
from odoo.addons.sol_onboarding.services.adapters.base import OrganisationValues
from odoo.addons.sol_onboarding.services.fetcher import Fetcher, SourceBusy
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

START = "https://lab.example/"
SECOND = "https://lab.example/page2"
ROBOTS = "https://lab.example/robots.txt"


def page(*rows, next_page=None):
    body = "".join(f'<tr data-key="{key}" data-tax-id="{tax}"><td>{name}</td></tr>' for key, name, tax in rows)
    link = f'<a rel="next" href="{next_page}">next</a>' if next_page else ""
    return 200, "text/html", f"<html><body><table>{body}</table>{link}</body></html>".encode(), {}


@tagged("post_install", "-at_install")
class TestOrganisations(OnboardingCase):
    def setUp(self):
        super().setUp()
        self.organisations = self.env[MODEL_ONBOARDING_ORGANISATION]
        self.suggest = self.organisations.with_context(**{SUGGEST_CONTEXT: True})

    def organisation(self, **values):
        values = {
            "source_id": self.source.id,
            "external_key": values.get("name", "x"),
            "name": "Laboratory",
            "url": START,
            "seen_at": fields.Datetime.now(),
            **values,
        }
        return self.organisations.sudo().create(values)

    def listed(self):
        return self.organisations.sudo().with_context(active_test=False).search([("source_id", "=", self.source.id)])

    def items(self):
        return self.env[MODEL_JOB_ITEM].search([("item_key", "=like", f"organisations:{self.source.id}:%")])

    def test_refresh_creates_and_updates_organisations_by_key(self):
        self.serve(
            {START: page(("a", "Alpha", "1"), ("b", "Beta", "2"), next_page=SECOND), SECOND: page(("c", "Gamma", "3"))}
        )
        self.run_until_settled(ORGANISATIONS_JOB)
        first = self.listed()
        self.assertEqual(sorted(first.mapped("name")), ["Alpha", "Beta", "Gamma"])
        alpha = first.filtered(lambda organisation: organisation.external_key == "a")
        seen = alpha.seen_at

        self.clock.tick(timedelta(weeks=1))
        self.serve(
            {
                START: page(("a", "Alpha Renamed", "1"), ("b", "Beta", "2"), next_page=SECOND),
                SECOND: page(("c", "Gamma", "3")),
            }
        )
        self.run_until_settled(ORGANISATIONS_JOB)

        self.assertEqual(self.listed(), first)
        self.assertEqual(alpha.name, "Alpha Renamed")
        self.assertGreater(alpha.seen_at, seen)

    def test_refresh_archives_organisations_no_longer_listed(self):
        self.serve({START: page(("a", "Alpha", "1"), ("b", "Beta", "2"))})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.clock.tick(timedelta(weeks=1))
        self.serve({START: page(("a", "Alpha", "1"))})
        self.run_until_settled(ORGANISATIONS_JOB)
        # The refresh after the one that missed it archives the organisation.
        self.clock.tick(timedelta(weeks=1))
        self.run_until_settled(ORGANISATIONS_JOB)

        active = {organisation.external_key: organisation.active for organisation in self.listed()}
        self.assertEqual(active, {"a": True, "b": False})

    def test_a_refresh_with_a_failed_page_archives_nothing_at_the_next(self):
        self.serve({START: page(("a", "Alpha", "1"), ("b", "Beta", "2"))})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.clock.tick(timedelta(weeks=1))
        self.serve({START: page(("a", "Alpha", "1"), next_page=SECOND)})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.assertIn("failed", self.items().mapped("status"))
        self.clock.tick(timedelta(weeks=1))
        self.run_until_settled(ORGANISATIONS_JOB)

        self.assertEqual(self.listed().mapped("active"), [True, True])

    def test_a_refresh_that_saw_nothing_archives_nothing_at_the_next(self):
        self.serve({START: page(("a", "Alpha", "1"), ("b", "Beta", "2"))})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.clock.tick(timedelta(weeks=1))
        self.serve({START: (200, "text/html", b"", {})})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.clock.tick(timedelta(weeks=1))
        self.run_until_settled(ORGANISATIONS_JOB)

        self.assertEqual(self.listed().mapped("active"), [True, True])

    def test_an_organisation_listed_again_comes_back(self):
        archived = self.organisation(external_key="a", name="Alpha", active=False)
        self.organisations.sudo()._upsert(self.source, [OrganisationValues(key="a", name="Alpha", url=START)])
        self.assertTrue(archived.active)

    def test_a_settled_refresh_is_not_queued_again_before_the_next_week(self):
        self.serve({START: page(("a", "Alpha", "1"))})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.run_until_settled(ORGANISATIONS_JOB)
        self.assertEqual(len(self.items()), 1)

        self.clock.tick(timedelta(weeks=1))
        self.run_until_settled(ORGANISATIONS_JOB)
        self.assertEqual(len(self.items()), 2)

    def test_a_refresh_stops_at_the_page_limit(self):
        self.source.page_limit = 2
        self.serve(
            {
                START: page(("a", "Alpha", "1"), next_page=SECOND),
                SECOND: page(("b", "Beta", "2"), next_page=START + "3"),
            }
        )
        self.run_until_settled(ORGANISATIONS_JOB)
        self.assertEqual(len(self.items()), 2)

    def test_an_empty_page_has_no_organisations(self):
        self.serve({START: (200, "text/html", b"", {})})
        self.run_until_settled(ORGANISATIONS_JOB)
        self.assertEqual(self.items().mapped("status"), ["done"])
        self.assertFalse(self.listed())

    def test_a_page_robots_txt_forbids_is_done_with_its_reason(self):
        self.serve({ROBOTS: (200, "text/plain", b"User-agent: *\nDisallow: /", {}), START: page(("a", "Alpha", "1"))})
        self.run_until_settled(ORGANISATIONS_JOB)
        item = self.items()
        self.assertEqual(item.status, "done")
        self.assertTrue(item.payload["skipped"])
        self.assertFalse(self.listed())

    def test_a_busy_source_defers_the_item_without_an_attempt(self):
        until = fields.Datetime.now() + timedelta(minutes=5)
        with patch.object(Fetcher, "fetch", side_effect=SourceBusy(until)):
            self.env["medilab.scheduled.job"]._by_key(ORGANISATIONS_JOB)._run_batch()
        item = self.items()
        self.assertEqual((item.status, item.attempts, item.next_attempt_at), ("pending", 0, until))

    def test_tax_id_match_is_the_first_suggestion(self):
        self.env.company.vat = "0101234567"
        match = self.organisation(tax_id="0101 234 567", name="Unrelated")
        self.organisation(name=self.env.company.name)

        result = self.suggest.name_search("")

        self.assertEqual(result[0][0], match.id)

    def test_suggestions_follow_name_similarity(self):
        self.env.company.vat = False
        self.env.company.name = "Trung tam kiem nghiem Alpha"
        far = self.organisation(name="Cong ty Zeta")
        near = self.organisation(name="Trung tam kiem nghiem Alpha 2")

        result = self.suggest.name_search("")

        self.assertEqual([id_ for id_, _ in result], [near.id, far.id])

    def test_suggestions_skip_archived_organisations_and_honour_the_domain(self):
        self.env.company.vat = False
        kept = self.organisation(name="Kept")
        self.organisation(name="Gone", active=False)
        other = self.organisation(name="Other")

        self.assertCountEqual([id_ for id_, _ in self.suggest.name_search("")], [kept.id, other.id])
        self.assertEqual([id_ for id_, _ in self.suggest.name_search("", [("id", "=", other.id)])], [other.id])

    def test_a_domain_matching_only_a_low_ranked_organisation_still_returns_it(self):
        self.env.company.vat = False
        self.env.company.name = "Alpha"
        self.organisation(name="Alpha")
        low = self.organisation(name="Zzz")

        result = self.suggest.name_search("", [("id", "=", low.id)], limit=1)

        self.assertEqual([id_ for id_, _ in result], [low.id])

    def test_a_typed_name_searches_as_usual(self):
        self.organisation(name="Alpha")
        beta = self.organisation(name="Beta")
        self.assertEqual([id_ for id_, _ in self.suggest.name_search("Bet")], [beta.id])

    def test_administrator_cannot_read_the_source_of_an_organisation(self):
        organisation = self.organisation()
        with self.assertRaises(AccessError):
            organisation.with_user(self.admin).read(["source_id"])
        self.assertNotIn("source_id", organisation.with_user(self.admin).fields_get())

    def test_every_user_reads_organisations(self):
        organisation = self.organisation()
        self.assertEqual(organisation.with_user(self.reader).read(["name"])[0]["name"], "Laboratory")

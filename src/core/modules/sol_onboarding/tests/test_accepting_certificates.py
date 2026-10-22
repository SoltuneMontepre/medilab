from datetime import datetime

from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_PARAMETER_GROUP,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ACCEPT,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import (
    KIND_CERTIFICATE,
    KIND_SAMPLE_TYPE,
    KIND_TEST_PARAMETER,
    KIND_TESTING_FIELD,
    KIND_TESTING_METHOD,
)
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

CERTIFICATE_CODE = "VILAS 9811"


@tagged("post_install", "-at_install")
class TestAcceptingCertificates(OnboardingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.field = cls.env[MODEL_TESTING_FIELD].create({"code": "ZZCERTFLD", "name": "Certificate field"})
        cls.other_field = cls.env[MODEL_TESTING_FIELD].create({"code": "ZZCERTOTH", "name": "Other certificate field"})

    def setUp(self):
        super().setUp()
        self.run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})

    def stage(self, *items):
        fetched = Fetched("https://lab.example/a", "html", b"<p>A</p>", datetime(2026, 10, 21, 8, 0, 0))
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(self.run, self.source, fetched)
        return self.env[MODEL_ONBOARDING_STAGED_RECORD]._stage(snapshot, items)

    def certificate(self, code=CERTIFICATE_CODE, **values):
        return StagedValues(KIND_CERTIFICATE, code, {"code": code, "issuing_body": "BoA", **values}, "vi_VN")

    def method(self, code, name, certificate=CERTIFICATE_CODE, **values):
        """A staged method of the certificate's scope."""
        return StagedValues(
            KIND_TESTING_METHOD,
            code,
            {"code": code, "name": name, **values},
            "vi_VN",
            parent=(KIND_CERTIFICATE, certificate),
        )

    def item(self, kind, value, **values):
        """A staged record outside the certificate: a testing field keyed by its code, the others by their name."""
        key = "code" if kind == KIND_TESTING_FIELD else "name"
        return StagedValues(kind, value, {key: value, **values}, "vi_VN")

    def lab_method(self, code, name):
        return self.env[MODEL_TESTING_METHOD].create({"code": code, "name": name, "field_id": self.other_field.id})

    def lab_certificate(self, staged):
        return self.env[MODEL_ACCREDITATION_CERTIFICATE].browse(staged.record_id).with_context(active_test=False)

    def test_a_certificate_with_thirty_methods_creates_twenty_five_and_links_thirty(self):
        codes = [f"TCVN 99{number:02d}:2012" for number in range(1, 31)]
        existing = self.env[MODEL_TESTING_METHOD]
        for code in codes[:5]:
            existing |= self.lab_method(code, f"Existing {code}")
        # One existing method is staged with its code written in another case and with other spaces.
        staged_codes = ["tcvn 9901 : 2012", *codes[1:]]
        names = [f"Existing {code}" for code in codes[:5]] + [f"New {code}" for code in codes[5:]]
        # The last ten new methods belong to a staged testing field; the others take the certificate's.
        methods = [
            self.method(code, name, **({"field_key": "ZZCERTNEW"} if index >= 20 else {}))
            for index, (code, name) in enumerate(zip(staged_codes, names, strict=True))
        ]
        staged = self.stage(
            self.certificate(), self.item(KIND_TESTING_FIELD, "ZZCERTNEW", name="New certificate field"), *methods
        )
        certificate, field, children = staged[0], staged[1], staged[2:]
        self.assertEqual(children.mapped("action"), ["link"] * 5 + ["create"] * 25)
        self.assertEqual(children.parent_id, certificate)
        certificate.field_id = self.field

        action = certificate.with_user(self.admin).action_accept()

        self.assertEqual(action["tag"], "display_notification")
        lab_certificate = self.lab_certificate(certificate)
        self.assertEqual((certificate.state, lab_certificate.code), ("accepted", CERTIFICATE_CODE))
        self.assertEqual(len(lab_certificate.method_ids), 30)
        lab_field = self.env[MODEL_TESTING_FIELD].browse(field.record_id)
        self.assertEqual((field.state, lab_field.code), ("accepted", "ZZCERTNEW"))
        created = lab_certificate.method_ids - existing
        self.assertEqual(
            {method.code: method.field_id for method in created},
            {code: self.field if index < 20 else lab_field for index, code in enumerate(codes) if index >= 5},
        )
        self.assertEqual(existing.mapped("name"), [f"Existing {code}" for code in codes[:5]])
        self.assertEqual(existing.mapped("field_id"), self.other_field)
        by_code = {method.code: method.id for method in lab_certificate.method_ids}
        self.assertEqual(children.mapped("state"), ["accepted"] * 30)
        self.assertEqual(children.mapped("record_id"), [by_code[code] for code in codes])
        self.assertEqual(children.mapped("reviewed_by_id"), self.admin)

    def test_certificate_links_methods_written_differently(self):
        method = self.lab_method("TCVN 9876:2011", "Written differently")
        method.active = False
        certificate, child = self.stage(self.certificate(), self.method("tcvn 9876 : 2011", "Written differently"))
        self.assertEqual((child.action, child.record_id), ("link", method.id))

        certificate.with_user(self.admin).action_accept()

        self.assertEqual(self.lab_certificate(certificate).method_ids, method)
        self.assertEqual((child.state, child.record_id), ("accepted", method.id))
        self.assertEqual((method.code, method.field_id, method.active), ("TCVN 9876:2011", self.other_field, False))
        written = self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search([("code", "ilike", "9876")])
        self.assertEqual(written, method)

    def test_child_updates_stay_to_review(self):
        method = self.lab_method("TCVN 9877:2012", "Old certificate title")
        certificate, changed, new = self.stage(
            self.certificate(),
            self.method("TCVN 9877:2012", "New certificate title"),
            self.method("TCVN 9878:2012", "Created with the certificate"),
        )
        self.assertEqual((changed.action, new.action), ("update", "create"))
        certificate.field_id = self.field

        certificate.with_user(self.admin).action_accept()

        lab_certificate = self.lab_certificate(certificate)
        self.assertEqual(lab_certificate.method_ids.mapped("code"), ["TCVN 9877:2012", "TCVN 9878:2012"])
        self.assertEqual((certificate.state, new.state), ("accepted", "accepted"))
        self.assertEqual((changed.state, changed.record_id), ("to_review", method.id))
        self.assertEqual(method.with_context(lang="vi_VN").name, "Old certificate title")

        changed.with_user(self.admin).action_accept()

        self.assertEqual(changed.state, "accepted")
        self.assertEqual(method.with_context(lang="vi_VN").name, "New certificate title")
        self.assertEqual(lab_certificate.method_ids, method | self.env[MODEL_TESTING_METHOD].browse(new.record_id))

    def test_new_methods_without_a_field_ask_for_one(self):
        certificate, first, second = self.stage(
            self.certificate(),
            self.method("TCVN 9879:2012", "Fieldless first"),
            self.method("TCVN 9880:2012", "Fieldless second"),
        )
        sample = self.stage(self.item(KIND_SAMPLE_TYPE, "Certificate sample xyz"))

        refused = (certificate | sample).with_user(self.admin).action_accept()

        self.assertEqual(refused["domain"], [("id", "in", certificate.ids)])
        self.assertEqual(certificate.error, f"Certificate {CERTIFICATE_CODE} needs these values first: Testing Field.")
        self.assertEqual((certificate | first | second).mapped("state"), ["to_review"] * 3)

        action = certificate.with_user(self.admin).action_accept()

        self.assertEqual(action["res_model"], MODEL_ONBOARDING_ACCEPT)
        wizard = (
            self.env[MODEL_ONBOARDING_ACCEPT]
            .with_user(self.admin)
            .with_context(action["context"])
            .create({"field_id": self.field.id})
        )
        self.assertTrue(wizard.field_needed)
        self.assertEqual(wizard.asked_for, f"Testing Field: Certificate {CERTIFICATE_CODE}")
        self.assertEqual(wizard.action_confirm()["tag"], "display_notification")
        self.assertEqual((certificate | first | second).mapped("state"), ["accepted"] * 3)
        self.assertFalse(certificate.error)
        created = self.env[MODEL_TESTING_METHOD].browse((first | second).mapped("record_id"))
        self.assertEqual(created.mapped("code"), ["TCVN 9879:2012", "TCVN 9880:2012"])
        self.assertEqual(created.mapped("field_id"), self.field)
        self.assertEqual(self.lab_certificate(certificate).method_ids, created)

    def test_a_deleted_method_match_leaves_the_certificate_to_review(self):
        method = self.lab_method("TCVN 9883:2012", "Deleted meanwhile")
        certificate, child = self.stage(self.certificate(), self.method("TCVN 9883:2012", "Deleted meanwhile"))
        method.unlink()

        certificate.with_user(self.admin).action_accept()

        self.assertEqual((certificate.state, child.state), ("to_review", "to_review"))
        self.assertEqual(
            certificate.error,
            "The matched record of Testing Method TCVN 9883:2012 no longer exists. Set the match again.",
        )
        self.assertFalse(self.env[MODEL_ACCREDITATION_CERTIFICATE].search([("code", "=", CERTIFICATE_CODE)]))

    def test_a_restaged_certificate_keeps_its_scope(self):
        methods = [self.method(f"TCVN 991{number}:2013", f"Kept method {number}") for number in range(3)]
        staged = self.stage(self.certificate(), *methods)
        old, children = staged[0], staged[1:]
        self.run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})

        new = self.stage(self.certificate(issuing_body="AOSC"), *methods)

        self.assertEqual((len(new), old.state), (1, "superseded"))
        self.assertEqual(new.child_ids, children)
        self.assertFalse(old.child_ids)
        new.field_id = self.field
        new.with_user(self.admin).action_accept()

        lab_certificate = self.lab_certificate(new)
        self.assertEqual((lab_certificate.issuing_body, len(lab_certificate.method_ids)), ("AOSC", 3))
        self.assertEqual(children.mapped("state"), ["accepted"] * 3)

    def test_methods_accepted_before_their_certificate_are_linked_to_it(self):
        certificate, first, second = self.stage(
            self.certificate(),
            self.method("TCVN 9921:2014", "Accepted before the certificate"),
            self.method("TCVN 9922:2014", "Accepted with the certificate"),
        )
        first.field_id = self.field
        first.with_user(self.admin).action_accept()
        self.assertEqual((certificate.state, first.state), ("to_review", "accepted"))
        certificate.field_id = self.field

        certificate.with_user(self.admin).action_accept()

        self.assertEqual((certificate | second).mapped("state"), ["accepted"] * 2)
        methods = self.env[MODEL_TESTING_METHOD].browse((first | second).mapped("record_id"))
        self.assertEqual(self.lab_certificate(certificate).method_ids, methods)

    def test_a_method_accepted_after_its_certificate_is_linked_to_it(self):
        certificate, first = self.stage(self.certificate(), self.method("TCVN 9923:2014", "In the first scope"))
        certificate.field_id = self.field
        certificate.with_user(self.admin).action_accept()
        self.run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})
        later = self.stage(self.method("TCVN 9924:2014", "Added to the scope later"))
        self.assertEqual(later.parent_id, certificate)
        later.field_id = self.field

        later.with_user(self.admin).action_accept()

        methods = self.env[MODEL_TESTING_METHOD].browse((first | later).mapped("record_id"))
        self.assertEqual((later.state, self.lab_certificate(certificate).method_ids), ("accepted", methods))

    def test_a_rejected_field_of_a_new_method_refuses_the_certificate(self):
        field, certificate, child = self.stage(
            self.item(KIND_TESTING_FIELD, "ZZCERTREJ", name="Rejected certificate field"),
            self.certificate(),
            self.method("TCVN 9884:2012", "Method of a rejected field", field_key="ZZCERTREJ"),
        )
        field.with_user(self.admin).action_reject("Not ours")
        message = "The staged Testing Field that Testing Method TCVN 9884:2012 needs is neither to review nor accepted."

        action = certificate.with_user(self.admin).action_accept()

        # Refused rather than asked for the certificate's testing field, which would not help.
        self.assertEqual(action["domain"], [("id", "in", certificate.ids)])
        self.assertEqual(certificate.error, message)
        certificate.field_id = self.field

        certificate.with_user(self.admin).action_accept()

        self.assertEqual(certificate.error, message)
        self.assertEqual((certificate.state, child.state), ("to_review", "to_review"))
        self.assertFalse(self.env[MODEL_TESTING_METHOD].search([("code", "=", "TCVN 9884:2012")]))

    def test_codes_written_differently_in_one_scope_make_one_method(self):
        certificate, first, second = self.stage(
            self.certificate(),
            self.method("TCVN 9902:2013", "Written once"),
            self.method("tcvn 9902 : 2013", "Written twice"),
        )
        certificate.field_id = self.field

        certificate.with_user(self.admin).action_accept()

        method = self.lab_certificate(certificate).method_ids
        self.assertEqual((method.code, method.field_id), ("TCVN 9902:2013", self.field))
        self.assertEqual((first | second).mapped("state"), ["accepted"] * 2)
        self.assertEqual((first | second).mapped("record_id"), [method.id] * 2)
        self.assertEqual(self.env[MODEL_TESTING_METHOD].search_count([("code", "ilike", "9902")]), 1)

    def test_accepting_twenty_with_two_refused_accepts_eighteen_and_lists_two(self):
        group = self.env[MODEL_PARAMETER_GROUP].create({"name": "Batch group"})
        staged = self.stage(
            self.certificate(),
            self.method("TCVN 9881:2012", "Batch method of the certificate one"),
            self.method("TCVN 9882:2012", "Batch method of the certificate two"),
            self.certificate("VILAS 9812", valid_from="2027-01-01", valid_until="2026-01-01"),
            *[self.item(KIND_TESTING_FIELD, f"ZZBATCH{number}", name=f"Batch field {number}") for number in range(5)],
            *[
                StagedValues(
                    KIND_TESTING_METHOD,
                    f"TCVN 989{number}:2012",
                    {"code": f"TCVN 989{number}:2012", "name": f"Batch method {number}", "field_key": "ZZBATCH0"},
                    "vi_VN",
                )
                for number in range(4)
            ],
            *[self.item(KIND_SAMPLE_TYPE, f"Batch sample qzx {number}") for number in range(4)],
            *[self.item(KIND_TEST_PARAMETER, f"Batch parameter qzx {number}") for number in range(3)],
        )
        self.assertEqual(len(staged), 20)
        certificate, dated_wrongly = staged[0], staged[3]
        certificate.field_id = self.field
        staged.filtered(lambda record: record.kind == KIND_TEST_PARAMETER).main_group_id = group
        # Laboratory gets a testing field with this code after it was staged.
        taken = staged.filtered(lambda record: record.external_key == "ZZBATCH4")
        self.env[MODEL_TESTING_FIELD].create({"code": "ZZBATCH4", "name": "Taken by Laboratory"})
        # In the list's order, newest first, so the methods come before their certificate.
        records = staged.browse(staged.ids[::-1])

        self.assertEqual((self.admin.lang, dated_wrongly.lang), ("en_US", "vi_VN"))

        # A refused constraint logs no error; the administrator's session is in English and the refused records are
        # staged in Vietnamese.
        with self.assertNoLogs("odoo.sql_db", level="ERROR"):
            action = records.with_user(self.admin).with_context(lang=self.admin.lang).action_accept()

        refused = dated_wrongly | taken
        self.assertEqual(action["res_model"], MODEL_ONBOARDING_STAGED_RECORD)
        self.assertEqual(staged.search(action["domain"]), refused)
        self.assertEqual(refused.mapped("state"), ["to_review"] * 2)
        self.assertEqual(
            dated_wrongly.error, "The first valid day of certificate VILAS 9812 cannot be after its last valid day."
        )
        self.assertEqual(taken.error, "The code of a testing field must be unique.")
        self.assertEqual((staged - refused).mapped("state"), ["accepted"] * 18)
        self.assertEqual(len(self.lab_certificate(certificate).method_ids), 2)

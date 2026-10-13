from datetime import date, datetime

from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.misc import format_amount, format_date, formatLang

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE

ENGLISH = "en_US"
VIETNAMESE = "vi_VN"


@tagged("post_install", "-at_install")
class TestLanguages(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.english_user = new_test_user(cls.env, "english.user", lang=ENGLISH)
        cls.vietnamese_user = new_test_user(cls.env, "vietnamese.user", lang=VIETNAMESE)
        cls.sample_type_model = cls.env["ir.model"]._get(MODEL_SAMPLE_TYPE)

    def test_setup_installs_english_and_vietnamese_with_their_translations(self):
        partner_name = self.env["ir.model.fields"]._get("res.partner", "name")

        self.assertLessEqual({ENGLISH, VIETNAMESE}, dict(self.env["res.lang"].get_installed()).keys())
        self.assertEqual(self.sample_type_model.with_context(lang=VIETNAMESE).name, "Loại Mẫu")
        self.assertNotEqual(
            partner_name.with_context(lang=VIETNAMESE).field_description,
            partner_name.with_context(lang=ENGLISH).field_description,
        )

    def test_user_language_choice_is_remembered(self):
        user = self.english_user.with_user(self.english_user)

        user.write({"lang": VIETNAMESE})

        self.assertEqual(user.context_get()["lang"], VIETNAMESE)

    def test_untranslated_text_falls_back_to_english(self):
        sample_type = self.env[MODEL_SAMPLE_TYPE].with_context(lang=ENGLISH).create({"code": "SW", "name": "Seawater"})

        self.assertEqual(sample_type.with_context(lang=VIETNAMESE).name, "Seawater")

    def test_dates_numbers_and_currency_follow_the_language(self):
        dollar = self.env.ref("base.USD")
        for lang, day, number in ((ENGLISH, "10/12/2026", "1,234.50"), (VIETNAMESE, "12/10/2026", "1.234,50")):
            with self.subTest(lang=lang):
                self.assertEqual(format_date(self.env, date(2026, 10, 12), lang_code=lang), day)
                self.assertEqual(formatLang(self.env(context={"lang": lang}), 1234.5), number)
                self.assertIn(number, format_amount(self.env, 1234.5, dollar, lang_code=lang))

    def test_adding_a_language_keeps_other_users_language(self):
        self.env.ref("base.lang_fr").action_unarchive()

        self.assertEqual(self.vietnamese_user.lang, VIETNAMESE)
        self.assertEqual(self.english_user.lang, ENGLISH)
        self.assertEqual(self.sample_type_model.with_context(lang=VIETNAMESE).name, "Loại Mẫu")
        self.assertEqual(self.sample_type_model.with_context(lang=ENGLISH).name, "Sample Type")

    def test_email_to_a_customer_is_in_their_language(self):
        customers = self.env["res.partner"].create(
            [
                {"name": "An Phat Foods", "email": "an.phat@example.com", "lang": VIETNAMESE},
                {"name": "Greenleaf Foods", "email": "greenleaf@example.com", "lang": ENGLISH},
            ]
        )
        event = self.env["calendar.event"].create(
            {"name": "Sample pickup", "start": datetime(2026, 10, 12, 9), "stop": datetime(2026, 10, 12, 10)}
        )
        vietnamese, english = self.env["calendar.attendee"].create(
            [{"event_id": event.id, "partner_id": customer.id} for customer in customers]
        )
        invitation = self.env.ref("calendar.calendar_template_meeting_invitation")

        langs = invitation._render_lang([vietnamese.id, english.id])
        subjects = invitation._render_field("subject", [vietnamese.id, english.id], compute_lang=True)

        self.assertEqual(langs, {vietnamese.id: VIETNAMESE, english.id: ENGLISH})
        self.assertEqual(subjects[english.id], "Invitation to Sample pickup")
        self.assertNotEqual(subjects[vietnamese.id], subjects[english.id])

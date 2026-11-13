from datetime import datetime, timedelta
from pathlib import Path

from odoo import fields
from odoo.modules.module import load_script
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MAIL_NOTIFICATION,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TASK_REMINDER, EVENT_TEST_REPORT_ISSUED
from odoo.addons.sol_laboratory.constants.settings import NOTICE_PORTAL_SINCE_PARAMETER

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.36.0" / "post-migrate.py"
CUTOVER = datetime(2026, 3, 1, 8, 0, 0)
SECOND = timedelta(seconds=1)


@tagged("post_install", "-at_install")
class TestNoticeCompatibility(TransactionCase):
    """A mandatory notice written by code that does not know the portal columns, such as an older pod during a release
    or an older image after a rollback, is shown to its recipient when it was written after the cutover. One written
    before it, and any notice with no recorded cutover, stays out."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref("base.group_portal")
        business = cls.env["res.partner"].create({"name": "An Phu", "is_company": True})
        cls.hoa = cls.account("Hoa", business, portal)
        cls.khoa = cls.account("Khoa", business, portal)
        cls.binh = cls.account("Binh", cls.env["res.partner"].create({"name": "Green"}), portal)
        cls.staff = cls.account("Staff", False, cls.env.ref("base.group_user"))
        subtype = cls.env[MODEL_MAIL_MESSAGE_SUBTYPE]
        cls.mandatory = subtype._event(EVENT_TEST_REPORT_ISSUED)
        cls.optional = subtype._event(EVENT_TASK_REMINDER)
        cls.document = cls.env["res.partner"].create({"name": "Document"})
        cls.keys = 0

    @classmethod
    def account(cls, name, parent, group, partner=None):
        login = f"compat.{name.lower()}"
        values = {"name": name, "login": login, "email": f"{login}@example.com", "group_ids": [(6, 0, group.ids)]}
        if partner:
            values["partner_id"] = partner.id
        user = cls.env["res.users"].create(values)
        if not partner:
            user.partner_id.write({"parent_id": parent.id if parent else False, "email": f"{login}@example.com"})
        return user

    def setUp(self):
        super().setUp()
        self.parameters = self.env[MODEL_IR_CONFIG_PARAMETER].sudo()
        self.parameters.set_str(NOTICE_PORTAL_SINCE_PARAMETER, CUTOVER.isoformat(sep=" "))

    def old_code_notice(self, user, written=CUTOVER + SECOND, event=None, date=None):
        """What code that does not know the columns leaves: the row's columns are empty. `written` is when its message
        was created, which Odoo sets and a caller cannot; `date` is the message's own date, which a caller can set."""
        self.keys += 1
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            (event or self.mandatory).code, self.document, f"compat:{self.keys}", "Body", partners=user.partner_id
        )
        row = message.notification_ids.filtered(lambda item: item.res_partner_id == user.partner_id)
        self.env.cr.execute(
            "UPDATE mail_notification SET portal_visible = NULL, portal_seen_at = NULL WHERE id = %s", (row.id,)
        )
        self.env.cr.execute(
            "UPDATE mail_message SET create_date = %s, date = %s WHERE id = %s",
            (written, date or written, message.id),
        )
        self.env.invalidate_all()
        return row

    def listed_for(self, user):
        rows = self.env[MODEL_MAIL_NOTIFICATION].sudo()
        return rows.search(rows._portal_domain(user))

    def migrate(self):
        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.35.0")
        self.env.transaction.invalidate_ormcache("stable")

    def recorded(self):
        self.env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (NOTICE_PORTAL_SINCE_PARAMETER,))
        rows = self.env.cr.fetchall()
        return rows[0][0] if rows else None

    # Old-code writers

    def test_a_mandatory_notice_old_code_wrote_after_the_cutover_is_shown_to_its_recipient(self):
        row = self.old_code_notice(self.hoa)
        self.assertFalse(row.portal_visible)
        self.assertIn(row, self.listed_for(self.hoa))

    def test_a_notice_whose_columns_a_rollback_dropped_is_still_shown(self):
        row = self.old_code_notice(self.hoa)
        self.assertEqual(row.notification_type, "email")
        self.assertIn(row, self.listed_for(self.hoa))

    def test_a_notice_old_code_wrote_for_a_contact_with_a_working_email_is_not_shown_to_anybody_else(self):
        row = self.old_code_notice(self.hoa)
        for user in (self.khoa, self.binh, self.staff):
            self.assertNotIn(row, self.listed_for(user))

    def test_a_notice_that_is_not_mandatory_stays_out_whoever_wrote_it(self):
        row = self.old_code_notice(self.hoa, event=self.optional)
        self.assertNotIn(row, self.listed_for(self.hoa))

    def test_an_internal_user_is_not_given_the_rule(self):
        row = self.old_code_notice(self.staff)
        self.assertNotIn(row, self.listed_for(self.staff))

    def test_a_recipient_old_code_wrote_no_row_for_gets_nothing(self):
        # Old code creates no row for a bounced contact. The rule reads rows; it cannot show one that was never written.
        self.binh.partner_id.email_bounced = True
        self.keys += 1
        message = (
            self.env[MODEL_MAIL_MESSAGE]
            .sudo()
            .create(
                {
                    "body": "Body",
                    "message_type": "notification",
                    "subtype_id": self.mandatory.id,
                    "notification_key": f"compat:{self.keys}",
                }
            )
        )
        self.assertFalse(message.notification_ids)
        self.assertFalse(self.listed_for(self.binh))

    def test_opening_a_notice_old_code_wrote_leaves_odoos_read_flag_and_the_document_alone(self):
        row = self.old_code_notice(self.hoa)
        written = self.document.write_date
        row._portal_open()
        self.assertTrue(row.portal_seen_at)
        self.assertFalse(row.is_read)
        self.assertEqual((row.notification_type, row.notification_status), ("email", "ready"))
        self.assertEqual(self.document.write_date, written)

    # The cutover boundary

    def test_a_notice_written_before_the_cutover_is_not_shown(self):
        before = self.old_code_notice(self.hoa, written=CUTOVER - SECOND)
        self.assertNotIn(before, self.listed_for(self.hoa))

    def test_a_notice_written_at_the_cutover_or_after_it_is_shown(self):
        at = self.old_code_notice(self.hoa, written=CUTOVER)
        after = self.old_code_notice(self.hoa, written=CUTOVER + timedelta(days=30))
        self.assertEqual(self.listed_for(self.hoa), at | after)

    def test_a_message_dated_in_the_past_but_written_after_the_cutover_is_shown(self):
        row = self.old_code_notice(self.hoa, written=CUTOVER + SECOND, date=CUTOVER - timedelta(days=400))
        self.assertIn(row, self.listed_for(self.hoa))

    def test_a_message_dated_in_the_future_but_written_before_the_cutover_is_not_shown(self):
        row = self.old_code_notice(self.hoa, written=CUTOVER - SECOND, date=CUTOVER + timedelta(days=400))
        self.assertNotIn(row, self.listed_for(self.hoa))

    def test_the_history_before_the_cutover_stays_out_whatever_its_number(self):
        history = [self.old_code_notice(self.hoa, written=CUTOVER - timedelta(days=day)) for day in range(1, 6)]
        self.assertFalse(
            self.listed_for(self.hoa) & self.env[MODEL_MAIL_NOTIFICATION].browse([row.id for row in history])
        )

    def test_an_email_notice_before_the_cutover_stays_out_but_an_inbox_one_stays_listed(self):
        email = self.old_code_notice(self.hoa, written=CUTOVER - SECOND)
        inbox = self.old_code_notice(self.hoa, written=CUTOVER - SECOND)
        inbox.write({"notification_type": "inbox"})
        self.assertEqual(self.listed_for(self.hoa), inbox)
        self.assertNotIn(email, self.listed_for(self.hoa))

    def test_a_notice_new_code_wrote_is_shown_whatever_the_cutover(self):
        self.keys += 1
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            self.mandatory.code, self.document, f"compat:{self.keys}", "Body", partners=self.hoa.partner_id
        )
        row = message.notification_ids
        self.assertTrue(row.portal_visible)
        self.parameters.set_str(NOTICE_PORTAL_SINCE_PARAMETER, "2999-01-01 00:00:00")
        self.assertIn(row, self.listed_for(self.hoa))

    # A cutover that is missing or unreadable

    def test_nothing_is_shown_without_a_recorded_cutover(self):
        row = self.old_code_notice(self.hoa)
        self.parameters.search([("key", "=", NOTICE_PORTAL_SINCE_PARAMETER)]).unlink()
        self.assertNotIn(row, self.listed_for(self.hoa))

    def test_nothing_is_shown_when_the_cutover_is_empty_or_not_a_date(self):
        row = self.old_code_notice(self.hoa)
        for value in ("", "   ", "yesterday", "2026-13-45 99:99:99", "2026-03-01T08:00:00+07:00"):
            self.parameters.set_str(NOTICE_PORTAL_SINCE_PARAMETER, value)
            self.assertNotIn(row, self.listed_for(self.hoa), value)

    # The migration

    def test_the_migration_records_the_cutover_and_a_notice_written_after_it_is_shown(self):
        self.parameters.search([("key", "=", NOTICE_PORTAL_SINCE_PARAMETER)]).unlink()
        self.migrate()
        recorded = self.recorded()
        self.assertTrue(recorded)
        self.assertLessEqual(fields_datetime(recorded), fields.Datetime.now())
        # A message written in the same transaction, after the upgrade began, carries the same moment.
        row = self.old_code_notice(self.hoa, written=fields_datetime(recorded))
        self.assertIn(row, self.listed_for(self.hoa))
        before = self.old_code_notice(self.hoa, written=fields_datetime(recorded) - SECOND)
        self.assertNotIn(before, self.listed_for(self.hoa))

    def test_the_cutover_survives_repeated_migrations(self):
        self.parameters.set_str(NOTICE_PORTAL_SINCE_PARAMETER, CUTOVER.isoformat(sep=" "))
        self.migrate()
        self.migrate()
        self.assertEqual(self.recorded(), CUTOVER.isoformat(sep=" "))

    def test_the_migration_does_not_show_the_notices_that_exist_before_it(self):
        old = self.old_code_notice(self.hoa, written=CUTOVER - timedelta(days=3))
        self.parameters.search([("key", "=", NOTICE_PORTAL_SINCE_PARAMETER)]).unlink()
        self.migrate()
        self.assertNotIn(old, self.listed_for(self.hoa))
        self.assertFalse(old.portal_visible)


def fields_datetime(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")

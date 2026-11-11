from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    COMMITTED,
    EXPIRE_JOB,
    EXPIRED,
    OPEN,
    SAVING,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import EDITED_ONLINE
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_LABORATORY_EDITING_IDLE_HOURS


@tagged("post_install", "-at_install")
class TestLaboratoryEditingExpiry(LaboratoryEditingCase):
    def setUp(self):
        super().setUp()
        self.session = self.new_session()

    def idle(self, hours, session=None):
        session = session or self.session
        session.sudo().last_activity_at = fields.Datetime.now() - timedelta(hours=hours)
        session.flush_recordset()

    def run_job(self):
        self.env[MODEL_SCHEDULED_JOB]._run_key(EXPIRE_JOB)

    def test_a_session_idle_for_12_hours_expires(self):
        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS - 1)
        self.run_job()
        self.assertEqual(self.session.status, OPEN)

        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1)
        self.run_job()

        self.assertEqual(self.session.status, EXPIRED)
        self.assertEqual(self.entries(self.session, "edit")[-1].change_ids.mapped("field_name"), ["status"])

    def test_a_session_stuck_saving_expires_too(self):
        self.session._keep_saving()
        self.assertEqual(self.session.status, SAVING)
        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1)

        self.run_job()

        self.assertEqual(self.session.status, EXPIRED)

    def test_the_retried_save_of_a_session_that_expired_while_saving_is_stored(self):
        self.session._keep_saving()
        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1)
        self.run_job()
        self.assertEqual(self.session.status, EXPIRED)

        version = self.session._store_save(content=self.stored("bản thử lại"), editor=self.tester, editors=self.tester)

        self.assertEqual((version.source, self.file.current_version_id), (EDITED_ONLINE, version))
        self.assertEqual((self.session.status, self.session.committed_version_id), (COMMITTED, version))

    def test_a_session_ended_by_its_save_never_expires(self):
        self.session._store_save(content=self.stored("bản 2"), editor=self.tester, editors=self.tester)
        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1)

        self.run_job()

        self.assertEqual(self.session.status, COMMITTED)

    def test_a_session_someone_worked_in_after_it_was_queued_does_not_expire_until_it_is_idle_again(self):
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(EXPIRE_JOB)
        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1)
        job._queue_laboratory_editing_sessions_expire()
        self.session._touch()
        job._run_batch()
        self.assertEqual(self.session.status, OPEN)

        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 2)
        job._run_batch()

        self.assertEqual(self.session.status, EXPIRED)

    def test_the_people_still_editing_an_expired_session_lose_nothing(self):
        self.idle(DEFAULT_LABORATORY_EDITING_IDLE_HOURS + 1)
        self.run_job()

        version = self.session._store_save(content=self.stored("13 giờ sửa"), editor=self.tester, editors=self.tester)

        self.assertEqual((self.session.status, self.file.current_version_id), (COMMITTED, version))

    def test_the_idle_period_is_at_least_1_hour(self):
        with self.assertRaises(ValidationError):
            self.env[MODEL_RES_CONFIG_SETTINGS].create({"laboratory_editing_idle_hours": 0})

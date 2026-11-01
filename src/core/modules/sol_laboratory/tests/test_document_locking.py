from datetime import timedelta
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import api, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.locks import LOCK_BUS_TYPE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_DOCUMENT_LOCK,
    MODEL_LOCK_MIXIN,
    MODEL_MAIL_MESSAGE,
    MODEL_PERMISSION_MIXIN,
    MODEL_REGULATION,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_LOCK_TIMEOUT_MINUTES, LOCK_TIMEOUT_PARAMETER
from odoo.addons.sol_laboratory.services.record_id import persisted_id

EXPIRE = "document_locks.expire"


@tagged("post_install", "-at_install")
class TestDocumentLocking(PeopleCase):
    """A regulation two people may edit: the chemist starts editing it first."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grant(cls.chemist, "regulation.edit.all")
        cls.grant(cls.microbiologist, "regulation.edit.all", "regulation.delete.all")
        cls.microbiologist.user_id.notification_type = "inbox"
        cls.regulation = cls.env[MODEL_REGULATION].create({"code": "QCVN 01-1:2018/BYT", "name": "Drinking water"})
        cls.administrator = cls.env.ref("base.user_admin")

    def as_chemist(self):
        return self.as_person(self.regulation, self.chemist)

    def as_microbiologist(self):
        return self.as_person(self.regulation, self.microbiologist)

    def lock(self):
        return self.env[MODEL_DOCUMENT_LOCK].search(
            [("document_model", "=", MODEL_REGULATION), ("document_id", "=", self.regulation.id)], limit=1
        )

    def idle(self, minutes):
        self.lock().last_activity_at = fields.Datetime.now() - timedelta(minutes=minutes)

    def test_a_second_user_sees_who_is_editing_and_cannot_save(self):
        self.assertEqual(self.as_chemist().lock_take(), {"taken": True})

        other = self.as_microbiologist()
        self.assertIn(self.chemist.name, other.lock_message)
        self.assertFalse(self.as_chemist().lock_message)
        refused = other.lock_take()
        self.assertFalse(refused["taken"])
        self.assertIn(self.chemist.name, refused["message"])
        with self.assertRaises(UserError):
            other.write({"name": "Bottled water"})
        with self.assertRaises(UserError):
            other.unlink()

    def test_saving_releases_the_lock_for_the_next_user(self):
        self.as_chemist().lock_take()

        self.as_chemist().write({"name": "Bottled water"})

        self.assertEqual((self.lock().status, self.lock().release_reason), ("released", "saved"))
        self.as_microbiologist().write({"name": "Mineral water"})
        self.assertEqual(self.regulation.name, "Mineral water")

    def test_cancelling_or_leaving_releases_the_lock(self):
        self.as_chemist().lock_take()
        self.as_chemist().lock_release("cancelled")
        self.assertEqual(self.lock().release_reason, "cancelled")

        self.as_chemist().lock_take()
        self.as_chemist().lock_release("left")
        self.assertEqual(self.lock().release_reason, "left")
        with self.assertRaises(UserError):
            self.as_chemist().lock_release("expired")

    def test_a_document_has_at_most_one_active_lock(self):
        self.as_chemist().lock_take()
        self.as_chemist().lock_take()
        self.assertEqual(len(self.env[MODEL_DOCUMENT_LOCK]._active(self.regulation)), 1)

        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env[MODEL_DOCUMENT_LOCK].create(
                {
                    "document_model": MODEL_REGULATION,
                    "document_id": self.regulation.id,
                    "user_id": self.administrator.id,
                }
            )
            self.env.flush_all()

    def test_a_lock_abandoned_by_a_closed_browser_expires_after_the_inactivity_period(self):
        self.as_chemist().lock_take()
        self.idle(DEFAULT_LOCK_TIMEOUT_MINUTES - 1)
        self.env[MODEL_SCHEDULED_JOB]._run_key(EXPIRE)
        self.assertEqual(self.lock().status, "active")

        self.idle(DEFAULT_LOCK_TIMEOUT_MINUTES + 1)
        self.env[MODEL_SCHEDULED_JOB]._run_key(EXPIRE)

        self.assertEqual((self.lock().status, self.lock().release_reason), ("expired", "expired"))
        self.as_microbiologist().write({"name": "Bottled water"})

    def test_an_abandoned_lock_does_not_block_before_the_job_runs(self):
        self.as_chemist().lock_take()
        self.idle(DEFAULT_LOCK_TIMEOUT_MINUTES + 1)

        self.assertFalse(self.as_microbiologist().lock_message)
        self.as_microbiologist().write({"name": "Bottled water"})
        self.assertEqual(self.lock().status, "expired")

    def test_the_inactivity_period_is_a_system_parameter(self):
        self.env["ir.config_parameter"].set_int(LOCK_TIMEOUT_PARAMETER, 30)
        self.as_chemist().lock_take()
        self.idle(DEFAULT_LOCK_TIMEOUT_MINUTES + 1)

        with self.assertRaises(UserError):
            self.as_microbiologist().write({"name": "Bottled water"})

    def test_the_inactivity_period_is_at_least_a_minute(self):
        with self.assertRaises(ValidationError):
            self.env[MODEL_RES_CONFIG_SETTINGS].create({"lock_timeout_minutes": 0})

    def test_a_lock_whose_holder_came_back_before_the_job_expires_when_it_goes_stale_again(self):
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(EXPIRE)
        self.as_chemist().lock_take()
        self.idle(DEFAULT_LOCK_TIMEOUT_MINUTES + 1)
        job._queue_document_locks_expire()
        self.as_chemist().lock_take()
        job._run_batch()
        self.assertEqual(self.lock().status, "active")

        self.idle(DEFAULT_LOCK_TIMEOUT_MINUTES + 2)
        job._run_batch()

        self.assertEqual(self.lock().status, "expired")

    def test_deleting_a_document_releases_the_own_lock(self):
        self.as_microbiologist().lock_take()
        lock = self.lock()

        self.as_microbiologist().unlink()

        self.assertEqual((lock.status, lock.release_reason), ("released", "left"))

    def test_a_watcher_is_notified_once_when_the_lock_is_released(self):
        self.as_chemist().lock_take()
        self.as_microbiologist().action_lock_watch()
        self.assertTrue(self.as_microbiologist().lock_watched)

        self.as_chemist().write({"name": "Bottled water"})
        self.as_chemist().lock_take()
        self.as_chemist().lock_release("left")

        released = self.env[MODEL_MAIL_MESSAGE].search([("notification_key", "=like", "document_lock:%:released")])
        self.assertEqual(len(released), 1)
        self.assertEqual(released.notification_ids.res_partner_id, self.microbiologist.user_id.partner_id)

    def test_watching_a_free_document_is_refused(self):
        with self.assertRaises(UserError):
            self.as_microbiologist().action_lock_watch()

    def test_taking_and_releasing_a_lock_is_sent_on_the_bus(self):
        with patch.object(type(self.env["bus.bus"]), "_sendone") as sent:
            self.as_chemist().lock_take()
            self.as_chemist().lock_release("left")

        payload = {"model": MODEL_REGULATION, "id": self.regulation.id}
        self.assertEqual([call.args[1:] for call in sent.call_args_list], [(LOCK_BUS_TYPE, payload)] * 2)

    def test_a_long_operation_started_twice_runs_once(self):
        locks = self.env[MODEL_DOCUMENT_LOCK]
        runs = []
        with locks._operation(self.regulation):
            runs.append("first")
            with self.assertRaises(UserError), locks._operation(self.regulation):
                runs.append("second")

        self.assertEqual(runs, ["first"])
        self.assertEqual((self.lock().kind, self.lock().release_reason), ("operation", "completed"))

    def test_a_concurrent_start_of_a_long_operation_is_refused_at_once(self):
        with self.env[MODEL_DOCUMENT_LOCK]._operation(self.regulation), self.registry.cursor() as cr:
            other = api.Environment(cr, persisted_id(self.administrator), {})
            with self.assertRaises(UserError):
                with other[MODEL_DOCUMENT_LOCK]._operation(
                    other[MODEL_REGULATION].browse(persisted_id(self.regulation))
                ):
                    self.fail("The second start ran.")

    def test_a_long_operation_waits_for_another_user_to_stop_editing(self):
        self.as_microbiologist().lock_take()

        with self.assertRaises(UserError):
            with self.env[MODEL_DOCUMENT_LOCK].with_user(self.chemist.user_id)._operation(self.regulation):
                self.fail("The operation ran while someone else edited the document.")

    def test_an_administrator_releases_a_stuck_lock_and_it_is_audited(self):
        self.as_chemist().lock_take()
        lock = self.lock()

        with self.assertRaises(AccessError):
            lock.with_user(self.microbiologist.user_id).action_release()
        lock.with_user(self.administrator).action_release()

        self.assertEqual(
            (lock.status, lock.release_reason, lock.released_by_id),
            ("released", "released_by_administrator", self.administrator),
        )
        entry = self.env[MODEL_AUDIT_ENTRY].search(
            [
                ("document_model", "=", MODEL_REGULATION),
                ("document_id", "=", self.regulation.id),
                ("action", "=", "unlock"),
            ]
        )
        self.assertEqual(entry.user_id, self.administrator)
        self.assertIn(self.chemist.user_id.name, (entry.note or ""))

    def test_the_form_shows_who_is_editing(self):
        arch = self.env[MODEL_REGULATION].get_view(view_type="form")["arch"]

        self.assertIn('name="lock_message"', arch)
        self.assertIn('name="action_lock_watch"', arch)

    def test_every_editable_laboratory_document_is_lockable(self):
        permission_mixin = type(self.env[MODEL_PERMISSION_MIXIN])
        lock_mixin = self.env.registry[MODEL_LOCK_MIXIN]
        unlockable = {
            name
            for name, model in self.env.registry.items()
            if not model._abstract
            and issubclass(model, permission_mixin)
            and "edit" in model._permission_actions
            and not issubclass(model, lock_mixin)
            and any(
                getattr(base, "_name", None) == name and getattr(base, "_module", None) == "sol_laboratory"
                for base in model.__mro__
            )
        }

        self.assertEqual(unlockable, {MODEL_DOCUMENT_LOCK})

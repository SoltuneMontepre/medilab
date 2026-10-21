import threading
import time
import uuid

from odoo import api, sql_db
from odoo.api import SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.http.retrying import retrying
from odoo.orm.environments import Transaction
from odoo.tests import TransactionCase
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_SAMPLE_TYPE, MODEL_TEST_REQUEST

# How long the first action keeps its transaction open once the second one is acting, so the second waits on it.
HOLD_SECONDS = 0.5
# Created without chatter entries, so removing the records leaves nothing behind.
QUIET = {"tracking_disable": True, "mail_create_nolog": True, "mail_notrack": True}


class LaboratoryFilesConcurrencyCase(TransactionCase):
    """Two real database transactions acting on laboratory files at once, the second one through Odoo's request
    retrying. What the tests commit is theirs to remove."""

    def committed(self, work):
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            return work(self.environment(cursor))

    def environment(self, cursor):
        # An environment looks its registry up by name, which waits on the lock the test run holds, so the thread of
        # these tests would never get one; they use the registry already loaded.
        cursor.transaction = Transaction(self.registry)
        cursor.transaction._check_signaling(cursor)
        return api.Environment(cursor, SUPERUSER_ID, {})

    def race(self, first_action, second_action):
        """The first action does its work and keeps its transaction open until the second one is acting, then commits.
        The second action runs as a request does, through Odoo's retrying. The number of times the second one ran, and
        the id of the record it returned or the refusal it was refused with."""
        stored = threading.Event()
        second_acting = threading.Event()
        errors = []

        def first():
            try:
                with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                    env = self.environment(cursor)
                    first_action(env)
                    env.flush_all()
                    # Committing resets the transaction, which also looks the registry up by name; the work is flushed,
                    # so the cursor commits it without one.
                    cursor.transaction = None
                    stored.set()
                    if not second_acting.wait(timeout=10):
                        errors.append(TimeoutError("the second action never started"))
                        return
                    time.sleep(HOLD_SECONDS)
            except Exception as error:
                errors.append(error)
            finally:
                stored.set()

        attempts = []
        thread = threading.Thread(target=first)
        thread.start()
        try:
            with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                env = self.environment(cursor)

                def run():
                    attempts.append(len(attempts) + 1)
                    if len(attempts) == 1:
                        self.assertTrue(stored.wait(timeout=10), "the first action never did its work")
                        second_acting.set()
                    return second_action(env).id

                with mute_logger("odoo.sql_db", "odoo.http"):
                    try:
                        result = retrying(run, env)
                    except UserError as refusal:
                        # The cursor would commit what the refused action did before it was refused.
                        cursor.rollback()
                        result = refusal
        finally:
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        return len(attempts), result

    @staticmethod
    def last_content(env):
        """The id of the last content recorded so far, from which remove_contents() removes what a test committed."""
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_laboratory_content")
        return env.cr.fetchone()[0]

    @staticmethod
    def remove_contents(cr, last_content_id):
        """Remove the contents recorded after last_content_id, once the versions referring to them are removed. Content
        refuses deletion, so it is removed with SQL; its bytes were never written to the bucket."""
        cr.execute("DELETE FROM medilab_laboratory_content WHERE id > %s", [last_content_id])

    @staticmethod
    def create_sample(env):
        """A customer's request with one sample, which a test commits and removes with remove_sample()."""
        env = env(context=QUIET)
        customer = env[MODEL_CUSTOMER].create({"name": f"Concurrency {uuid.uuid4().hex[:8]}", "is_company": True})
        sample_type = env[MODEL_SAMPLE_TYPE].create({"name": f"Concurrency {uuid.uuid4().hex[:8]}"})
        request = env[MODEL_TEST_REQUEST].create(
            {
                "customer_id": customer.id,
                "expected_date": "2026-10-20",
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": "Lavie bottled water 1 L",
                            "sample_type_id": sample_type.id,
                            "physical_state": "liquid",
                        }
                    )
                ],
            }
        )
        return {
            "customer": customer.id,
            "partner": customer.partner_id.id,
            "sample_type": sample_type.id,
            "request": request.id,
            "sample": request.sample_ids.id,
        }

    @staticmethod
    def remove_sample(cr, sample):
        """Remove a sample create_sample() made, and its folders once their files are removed. Folders, samples and
        requests refuse deletion, so they are removed with SQL."""
        cr.execute(
            "DELETE FROM medilab_laboratory_folder_member WHERE folder_id IN "
            "(SELECT id FROM medilab_laboratory_folder WHERE sample_id = %s)",
            [sample["sample"]],
        )
        cr.execute("DELETE FROM medilab_laboratory_folder WHERE sample_id = %s", [sample["sample"]])
        cr.execute("DELETE FROM medilab_sample WHERE id = %s", [sample["sample"]])
        cr.execute("DELETE FROM medilab_test_request WHERE id = %s", [sample["request"]])
        cr.execute("DELETE FROM medilab_sample_type WHERE id = %s", [sample["sample_type"]])
        cr.execute("DELETE FROM medilab_customer WHERE id = %s", [sample["customer"]])
        cr.execute("DELETE FROM res_partner WHERE id = %s", [sample["partner"]])

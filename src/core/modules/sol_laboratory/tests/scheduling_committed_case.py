import uuid
from datetime import timedelta

from odoo import api, fields, sql_db
from odoo.api import SUPERUSER_ID
from odoo.fields import Command, Domain
from odoo.orm.environments import Transaction
from odoo.tests import TransactionCase
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_CALENDAR_EVENT,
    MODEL_CUSTOMER,
    MODEL_DEPARTMENT,
    MODEL_LABORATORY_FOLDER,
    MODEL_LOCATION,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TYPE,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
    MODEL_TEST_REQUEST,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
    MODEL_UNIT_CATEGORY,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_PERSON

QUIET = {"tracking_disable": True, "mail_create_nolog": True, "mail_notrack": True}
PASSWORD = "scheduling-transaction-test"


class SchedulingCommittedCase(TransactionCase):
    """Owned fixtures committed outside the test cursor, shared by races and normal HTTP rollback checks."""

    def environment(self, cursor):
        # The test runner holds the registry lock; worker threads use its already loaded registry.
        cursor.transaction = Transaction(self.registry)
        cursor.transaction._check_signaling(cursor)
        return api.Environment(cursor, SUPERUSER_ID, QUIET)

    def committed(self, work):
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            env = self.environment(cursor)
            result = work(env)
            cursor.flush()
            cursor.transaction = None
            return result

    def setUp(self):
        super().setUp()
        self.owned = {}
        self.workers = []
        self.token = uuid.uuid4().hex[:12]
        self.committed(self.prepare)
        self.addCleanup(self.remove_committed)

    def create(self, env, model, values):
        records = env[model].create(values)
        self.owned.setdefault(model, []).extend(records.ids)
        return records

    def prepare(self, env):
        def create(model, values):
            return self.create(env, model, values)

        department = create(MODEL_DEPARTMENT, {"name": f"Scheduling {self.token}"})
        self.department_id = department.id
        users = create(
            "res.users",
            [
                {
                    "name": f"Scheduling actor {number} {self.token}",
                    "login": f"scheduling.{self.token}.{number}",
                    "password": PASSWORD,
                    "group_ids": [Command.set(env.ref("base.group_user").ids)],
                }
                for number in (1, 2)
            ],
        )
        people = create(
            MODEL_PERSON,
            [
                {
                    "name": f"Scheduling actor {number} {self.token}",
                    "department_id": department.id,
                    "user_id": users[number - 1].id,
                    "tz": "UTC",
                    "permission_ids": [Command.set([env.ref("sol_laboratory.permission_sample_test_read_all").id])],
                }
                for number in (1, 2)
            ],
        )
        self.person_ids, self.user_ids = people.ids, people.user_id.ids
        self.partner_ids = [person.user_id.partner_id.id for person in people]
        self.logins = people.user_id.mapped("login")
        self.owned["hr.employee"] = people.employee_id.ids
        self.owned["resource.resource"] = people.employee_id.resource_id.ids
        self.owned["res.users"] = people.user_id.ids
        self.owned["res.partner"] = (people.user_id.partner_id | people.work_contact_id).ids
        category = create(MODEL_UNIT_CATEGORY, {"name": f"Scheduling unit {self.token}"})
        unit = create(MODEL_MEASUREMENT_UNIT, {"name": f"mg/L {self.token}", "category_id": category.id})
        field = create(MODEL_TESTING_FIELD, {"code": self.token, "name": "Scheduling"})
        method = create(
            MODEL_TESTING_METHOD,
            {"code": self.token, "name": "Scheduling method", "field_id": field.id},
        )
        group = create(MODEL_PARAMETER_GROUP, {"name": f"Scheduling group {self.token}"})
        parameter = create(
            MODEL_TEST_PARAMETER,
            {"name": f"Scheduling parameter {self.token}", "group_ids": [group.id], "main_group_id": group.id},
        )
        pair = create(
            MODEL_PARAMETER_METHOD,
            {"parameter_id": parameter.id, "method_id": method.id, "department_id": department.id},
        )
        sample_type = create(MODEL_SAMPLE_TYPE, {"name": f"Scheduling sample type {self.token}"})
        create(
            MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
            {
                "parameter_id": parameter.id,
                "parameter_method_id": pair.id,
                "sample_type_id": sample_type.id,
                "unit_id": unit.id,
                "is_default": True,
            },
        )
        machine = create(MODEL_MACHINE, {"code": self.token, "name": f"Scheduling machine {self.token}"})
        self.machine_id = machine.id
        create(
            MODEL_PARAMETER_METHOD_MACHINE,
            {"parameter_method_id": pair.id, "machine_id": machine.id, "run_minutes": 40},
        )
        room = create(MODEL_LOCATION, {"code": self.token, "name": "Scheduling room", "is_bookable": True})
        self.room_id = room.id
        create(
            MODEL_TESTING_METHOD_STEP,
            {
                "method_id": method.id,
                "sequence": 1,
                "instruction": "Prepare",
                "duration_minutes": 30,
                "location_id": room.id,
            },
        )
        customer = create(MODEL_CUSTOMER, {"name": f"Scheduling customer {self.token}", "is_company": True})
        self.owned["res.partner"].extend(customer.partner_id.ids)
        request = create(
            MODEL_TEST_REQUEST,
            {
                "customer_id": customer.id,
                "expected_date": fields.Date.today() + timedelta(days=60),
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": f"Scheduling sample {number}",
                            "sample_type_id": sample_type.id,
                            "physical_state": "liquid",
                            "test_ids": [Command.create({"parameter_id": parameter.id})],
                        }
                    )
                    for number in (1, 2)
                ],
            },
        )
        self.owned[MODEL_SAMPLE] = request.sample_ids.ids
        tests = request.sample_ids.test_ids.sorted("id")
        self.owned[MODEL_SAMPLE_TEST] = self.test_ids = tests.ids
        administrator = env.ref(ADMINISTRATOR_PERSON).user_id
        request.with_user(administrator).action_confirm()
        request.sample_ids.with_user(administrator).action_receive("1 vial", "good")
        tasks = env[MODEL_TASK].search(
            [("document_model", "=", MODEL_SAMPLE_TEST), ("document_id", "in", self.test_ids)], order="id"
        )
        self.assertEqual(len(tasks), 2)
        self.owned[MODEL_TASK] = self.task_ids = tasks.ids

    def assign(self, env, number=0):
        task = env[MODEL_TASK].browse(self.task_ids[number])
        task.write({"assignee_id": self.person_ids[number], "status": "assigned"})

    def graph(self, env):
        tasks = env[MODEL_TASK].browse(self.task_ids)
        tests = env[MODEL_SAMPLE_TEST].browse(self.test_ids)
        bookings = env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "in", self.test_ids)], order="id")
        events = (
            env[MODEL_CALENDAR_EVENT].search([("user_id", "in", self.user_ids)])
            | bookings.calendar_event_id
            | bookings.room_event_ids
        ).sorted("id")
        return {
            "tasks": tasks.read(
                ["status", "assignee_id", "assigned_by_id", "planned_start", "planned_end", "write_date"]
            ),
            "tests": tests.read(["status", "parameter_method_id", "outsourcing_suggested", "write_date"]),
            "bookings": bookings.read(
                [
                    "status",
                    "person_id",
                    "machine_id",
                    "starts_at",
                    "ends_at",
                    "calendar_event_id",
                    "room_event_ids",
                    "write_date",
                ]
            ),
            "events": events.read(
                ["start", "stop", "user_id", "partner_ids", "machine_booking_id", "location_id", "write_date"]
            ),
            "messages": env["mail.message"].search_read(
                [("model", "=", MODEL_TASK), ("res_id", "in", self.task_ids)],
                ["res_id", "notification_ids"],
                order="id",
            ),
            "audit": env[MODEL_AUDIT_ENTRY].search_read(
                [("document_model", "=", MODEL_TASK), ("document_id", "in", self.task_ids)],
                ["action", "document_id"],
                order="id",
            ),
        }

    def remove_committed(self):
        self.assertFalse(
            any(thread.is_alive() for thread in self.workers), "Cannot clean fixtures while a worker is live"
        )

        def remove(env):
            bookings = env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "in", self.test_ids)])
            self.owned[MODEL_MACHINE_BOOKING] = bookings.ids
            self.owned[MODEL_CALENDAR_EVENT] = (
                env[MODEL_CALENDAR_EVENT].search([("user_id", "in", self.user_ids)])
                | bookings.calendar_event_id
                | bookings.room_event_ids
            ).ids
            folders = env[MODEL_LABORATORY_FOLDER].search([("sample_id", "in", self.owned[MODEL_SAMPLE])])
            self.owned[MODEL_LABORATORY_FOLDER] = folders.ids
            self.owned["calendar.user"] = env["calendar.user"].search([("user_id", "in", self.user_ids)]).ids
            messages = Domain.OR(
                [Domain("model", "=", model) & Domain("res_id", "in", ids) for model, ids in self.owned.items() if ids]
                + [
                    Domain("author_id", "in", self.owned["res.partner"]),
                    Domain("partner_ids", "in", self.owned["res.partner"]),
                    Domain("notification_ids.res_partner_id", "in", self.owned["res.partner"]),
                ]
            )
            self.owned["mail.message"] = env["mail.message"].search(messages).ids
            # These documents forbid ordinary deletion. Remove only this fixture's exact committed IDs and audit rows.
            owned = SQL(" OR ").join(
                SQL("(document_model = %s AND document_id = ANY(%s))", model, ids)
                for model, ids in self.owned.items()
                if ids
            )
            env.cr.execute(
                SQL(
                    "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE %s)",
                    owned,
                )
            )
            env.cr.execute(SQL("DELETE FROM medilab_audit_entry WHERE %s", owned))
            for model in (
                "mail.message",
                MODEL_CALENDAR_EVENT,
                MODEL_MACHINE_BOOKING,
                MODEL_TASK,
                MODEL_LABORATORY_FOLDER,
                MODEL_SAMPLE_TEST,
                MODEL_SAMPLE,
                MODEL_TEST_REQUEST,
                MODEL_CUSTOMER,
                MODEL_PARAMETER_METHOD_MACHINE,
                MODEL_TESTING_METHOD_STEP,
                MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
                MODEL_PARAMETER_METHOD,
                MODEL_TEST_PARAMETER,
                MODEL_PARAMETER_GROUP,
                MODEL_TESTING_METHOD,
                MODEL_TESTING_FIELD,
                MODEL_MEASUREMENT_UNIT,
                MODEL_UNIT_CATEGORY,
                MODEL_SAMPLE_TYPE,
                MODEL_MACHINE,
                MODEL_LOCATION,
                MODEL_PERSON,
                "hr.employee",
                "resource.resource",
                "calendar.user",
                "res.users",
                "res.partner",
                MODEL_DEPARTMENT,
            ):
                if ids := self.owned.get(model):
                    env.cr.execute(SQL("DELETE FROM %s WHERE id = ANY(%s)", SQL.identifier(env[model]._table), ids))

        self.committed(remove)

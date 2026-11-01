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
    MODEL_CALENDAR_USER,
    MODEL_CUSTOMER,
    MODEL_DEPARTMENT,
    MODEL_EMPLOYEE,
    MODEL_IR_ATTACHMENT,
    MODEL_LABORATORY_FOLDER,
    MODEL_LOCATION,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_PERSON,
    MODEL_RES_PARTNER,
    MODEL_RES_USERS,
    MODEL_RESOURCE,
    MODEL_SAMPLE,
    MODEL_SAMPLE_HANDOVER,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TYPE,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
    MODEL_TEST_PARAMETER,
    MODEL_TEST_REQUEST,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
    MODEL_UNIT_CATEGORY,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_PERSON
from odoo.addons.sol_laboratory.services.record_id import persisted_id, persisted_ids

QUIET = {"tracking_disable": True, "mail_create_nolog": True, "mail_notrack": True}
PASSWORD = "scheduling-transaction-test"
HEAD_PERMISSIONS = (
    "task_read_own_department",
    "task_edit_own_department",
    "machine_booking_read_own_department",
    "machine_booking_create_own_department",
    "machine_booking_edit_own_department",
)
# The columns of other tests' queued bookings, and of their tests, that a replan of the queue can write.
FOREIGN_COLUMNS = {
    "medilab_machine_booking": (
        "status",
        "machine_id",
        "person_id",
        "starts_at",
        "ends_at",
        "calendar_event_id",
        "write_uid",
        "write_date",
    ),
    "medilab_sample_test": ("status", "parameter_method_id", "outsourcing_suggested", "write_uid", "write_date"),
}
COUNTED_TABLES = (
    "medilab_machine_booking",
    "calendar_event",
    "medilab_audit_entry",
    "medilab_audit_change",
    "ir_attachment",
    "mail_message",
    "mail_notification",
)


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
            MODEL_RES_USERS,
            [
                {
                    "name": f"Scheduling actor {number} {self.token}",
                    "login": f"scheduling.{self.token}.{number}",
                    "password": PASSWORD,
                    "group_ids": [Command.set(persisted_ids(env.ref("base.group_user")))],
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
                    "permission_ids": [
                        Command.set([persisted_id(env.ref("sol_laboratory.permission_sample_test_read_all"))])
                    ],
                }
                for number in (1, 2)
            ],
        )
        self.person_ids, self.user_ids = people.ids, people.user_id.ids
        self.partner_ids = [person.user_id.partner_id.id for person in people]
        self.logins = people.user_id.mapped("login")
        self.owned.setdefault(MODEL_EMPLOYEE, []).extend(people.employee_id.ids)
        self.owned.setdefault(MODEL_RESOURCE, []).extend(people.employee_id.resource_id.ids)
        self.owned.setdefault(MODEL_RES_USERS, []).extend(people.user_id.ids)
        self.owned.setdefault(MODEL_RES_PARTNER, []).extend((people.user_id.partner_id | people.work_contact_id).ids)
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
            {
                "parameter_id": parameter.id,
                "method_id": method.id,
                "unit_id": unit.id,
                "department_id": department.id,
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
        self.owned[MODEL_RES_PARTNER].extend(customer.partner_id.ids)
        sample_type = create(MODEL_SAMPLE_TYPE, {"name": f"Scheduling sample type {self.token}"})
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
        self.owned.setdefault(MODEL_SAMPLE, []).extend(request.sample_ids.ids)
        tests = request.sample_ids.test_ids.sorted("id")
        self.test_ids = tests.ids
        self.owned.setdefault(MODEL_SAMPLE_TEST, []).extend(tests.ids)
        administrator = env.ref(ADMINISTRATOR_PERSON).user_id
        request.with_user(administrator).action_confirm()
        request.sample_ids.with_user(administrator).action_receive("1 vial", "good")
        tasks = env[MODEL_TASK].search(
            [("document_model", "=", MODEL_SAMPLE_TEST), ("document_id", "in", self.test_ids)], order="id"
        )
        self.assertEqual(len(tasks), 2)
        self.task_ids = tasks.ids
        self.owned.setdefault(MODEL_TASK, []).extend(tasks.ids)

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
            "messages": env[MODEL_MAIL_MESSAGE].search_read(
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

    def assert_committed_invariants(self, env):
        """The committed scheduling state of the fixture's tests, machine and room keeps the rules every schedule keeps
        (plan invariants P1-P5 and P8 in SQL, P7 and P9 on records), read on the given cursor."""
        active = ("scheduled", "in_progress")
        checks = {
            "P1: bookings of the machine overlap": SQL(
                "SELECT a.id FROM medilab_machine_booking a JOIN medilab_machine_booking b ON a.machine_id = b.machine_id"
                " AND a.id < b.id AND tsrange(a.starts_at, a.ends_at) && tsrange(b.starts_at, b.ends_at)"
                " WHERE a.machine_id = %s AND a.status IN %s AND b.status IN %s",
                self.machine_id,
                active,
                active,
            ),
            "P2: bookings of the room overlap": SQL(
                "SELECT a.id FROM calendar_event a JOIN calendar_event b ON a.location_id = b.location_id"
                " AND a.id < b.id AND tsrange(a.start, a.stop) && tsrange(b.start, b.stop)"
                " WHERE a.location_id = %s AND a.active AND b.active",
                self.room_id,
            ),
            "P3: an active booking has no slot on a 15-minute boundary": SQL(
                "SELECT id FROM medilab_machine_booking WHERE sample_test_id = ANY(%s) AND status IN %s"
                " AND (starts_at IS NULL OR ends_at IS NULL OR ends_at <= starts_at"
                " OR date_trunc('minute', starts_at) <> starts_at OR EXTRACT(MINUTE FROM starts_at)::int %% 15 <> 0)",
                self.test_ids,
                active,
            ),
            "P4: a test has more than one open booking": SQL(
                "SELECT sample_test_id FROM medilab_machine_booking WHERE sample_test_id = ANY(%s)"
                " AND status IN ('queued', 'scheduled', 'in_progress') GROUP BY 1 HAVING count(*) > 1",
                self.test_ids,
            ),
            "P5: a booking's person is not its task's assignee": SQL(
                "SELECT b.id FROM medilab_machine_booking b JOIN medilab_task t ON t.id = b.task_id"
                " WHERE b.sample_test_id = ANY(%s) AND b.status IN ('queued', 'scheduled')"
                " AND b.person_id IS DISTINCT FROM t.assignee_id",
                self.test_ids,
            ),
            "P8: a closed test has an open booking": SQL(
                "SELECT b.id FROM medilab_machine_booking b JOIN medilab_sample_test s ON s.id = b.sample_test_id"
                " WHERE b.sample_test_id = ANY(%s) AND b.status IN ('queued', 'scheduled', 'in_progress')"
                " AND s.status IN ('cancelled', 'outsourced', 'approved', 'result_entered')",
                self.test_ids,
            ),
        }
        for message, query in checks.items():
            env.cr.execute(query)
            self.assertFalse(env.cr.fetchall(), message)
        for booking in env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "in", self.test_ids)]):
            label = f"booking {booking.id} ({booking.status})"
            if booking.status not in ("scheduled", "in_progress"):
                if booking.status != "done":
                    self.assertFalse(booking.calendar_event_id | booking.room_event_ids, f"P7: {label} keeps events")
                continue
            event = booking.calendar_event_id
            self.assertEqual(
                (event.start, event.stop, event.user_id, event.alarm_ids.ids),
                (booking.starts_at, booking.ends_at, booking.person_id.user_id, []),
                f"P7: the person event does not follow {label}",
            )
            steps = booking._room_steps(booking.sample_test_id.parameter_method_id)
            self.assertEqual(
                sorted((room.location_id.id, room.start, room.stop) for room in booking.room_event_ids),
                sorted(
                    (step.location_id.id, booking.starts_at + offset, booking.starts_at + offset + length)
                    for step, offset, length in steps
                ),
                f"P7: the room events do not follow {label}",
            )
            if booking.status == "scheduled":
                self.assertLessEqual(
                    booking.ends_at, booking.machine_id._usable_until(), f"P9: {label} ends after its machine is fit"
                )
        for task in env[MODEL_TASK].browse(self.task_ids):
            slots = task.booking_ids.filtered(lambda booking: booking.status != "cancelled" and booking.starts_at)
            self.assertEqual(
                (task.planned_start, task.planned_end),
                (min(slots.mapped("starts_at"), default=False), max(slots.mapped("ends_at"), default=False)),
                f"P7: the planned time of task {task.id} does not follow its bookings",
            )

    def keep_foreign_queue(self, env):
        """Leave other tests' queued bookings in the queue, so every replan in the test meets them, and put their rows
        and their tests' rows back as they were when the test ends. Returns their ids and those rows.

        Only bookings that no machine can place are kept: a placed one would gain events the restore does not remove.
        """
        bookings = (
            env[MODEL_MACHINE_BOOKING]
            .sudo()
            .search([("status", "=", "queued"), ("sample_test_id", "not in", self.owned[MODEL_SAMPLE_TEST])])
        )
        for booking in bookings:
            found = booking._recommend(booking.sample_test_id, booking.person_id, booking.department_id)
            self.assertIsNone(found, f"Queued booking {booking.id} could be placed by a replan")
        ids = {"medilab_machine_booking": bookings.ids, "medilab_sample_test": bookings.sample_test_id.ids}
        before = self.foreign_rows(env, ids)

        def restore(env):
            for table, rows in before.items():
                for row_id, values in rows.items():
                    assignments = SQL(", ").join(
                        SQL("%s = %s", SQL.identifier(column), value) for column, value in values.items()
                    )
                    env.cr.execute(SQL("UPDATE %s SET %s WHERE id = %s", SQL.identifier(table), assignments, row_id))
            self.assertEqual(self.foreign_rows(env, ids), before, "A foreign queued booking was not restored")

        self.addCleanup(self.committed, restore)
        return ids, before

    @staticmethod
    def foreign_rows(env, ids):
        """The rows of the ids, {table: [ids]}, as {table: {id: {column: value}}}, with FOREIGN_COLUMNS."""
        rows = {}
        for table, columns in FOREIGN_COLUMNS.items():
            env.cr.execute(
                SQL(
                    "SELECT id, %s FROM %s WHERE id = ANY(%s) ORDER BY id",
                    SQL(", ").join(map(SQL.identifier, columns)),
                    SQL.identifier(table),
                    ids[table],
                )
            )
            rows[table] = {row[0]: dict(zip(columns, row[1:], strict=True)) for row in env.cr.fetchall()}
        return rows

    def table_counts(self, env):
        """The number of rows and the last id of each table a schedule writes to, in the whole database."""
        counts = {}
        for table in COUNTED_TABLES:
            env.cr.execute(SQL("SELECT count(*), max(id) FROM %s", SQL.identifier(table)))
            counts[table] = env.cr.fetchone()
        return counts

    def grant(self, env, number, codes):
        """Give the fixture's person of the number the permissions of the codes, such as task_edit_own_department."""
        env[MODEL_PERSON].browse(self.person_ids[number]).permission_ids = [
            Command.link(env.ref(f"sol_laboratory.permission_{code}").id) for code in codes
        ]

    def assert_consistent_booking(self, graph, number):
        """The fixture's test of the number has one scheduled booking, which its task, person event and room follow."""
        task = graph["tasks"][number]
        [booking] = [booking for booking in graph["bookings"] if booking["person_id"][0] == self.person_ids[number]]
        self.assertEqual(booking["status"], "scheduled")
        self.assertEqual(booking["machine_id"][0], self.machine_id)
        self.assertEqual(task["status"], "assigned")
        self.assertEqual(task["assignee_id"][0], self.person_ids[number])
        self.assertEqual(graph["tests"][number]["status"], "assigned")
        self.assertEqual((task["planned_start"], task["planned_end"]), (booking["starts_at"], booking["ends_at"]))
        [event] = [event for event in graph["events"] if event["id"] == booking["calendar_event_id"][0]]
        self.assertEqual((event["start"], event["stop"]), (booking["starts_at"], booking["ends_at"]))
        self.assertEqual(event["user_id"][0], self.user_ids[number])
        self.assertEqual(event["partner_ids"], [self.partner_ids[number]])
        [room] = [event for event in graph["events"] if event["id"] in booking["room_event_ids"]]
        self.assertEqual(room["location_id"][0], self.room_id)
        self.assertEqual(room["machine_booking_id"][0], booking["id"])
        self.assertEqual(room["start"], booking["starts_at"])
        self.assertEqual(room["stop"] - room["start"], timedelta(minutes=30))
        self.assertEqual(room["user_id"][0], self.user_ids[number])
        self.assertEqual(room["partner_ids"], [self.partner_ids[number]])

    def remove_committed(self):
        self.assertFalse(
            any(thread.is_alive() for thread in self.workers), "Cannot clean fixtures while a worker is live"
        )

        def remove(env):
            # Every fixture this test prepared, not only the last one, which the ids on self name.
            user_ids = self.owned[MODEL_RES_USERS]
            bookings = env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "in", self.owned[MODEL_SAMPLE_TEST])])
            self.owned[MODEL_MACHINE_BOOKING] = bookings.ids
            # With the events a test recorded before production code deleted them, whose audit rows go below.
            events = (
                env[MODEL_CALENDAR_EVENT].search([("user_id", "in", user_ids)])
                | bookings.calendar_event_id
                | bookings.room_event_ids
            )
            self.owned[MODEL_CALENDAR_EVENT] = sorted(set(self.owned.get(MODEL_CALENDAR_EVENT, [])) | set(events.ids))
            folders = env[MODEL_LABORATORY_FOLDER].search([("sample_id", "in", self.owned[MODEL_SAMPLE])])
            self.owned[MODEL_LABORATORY_FOLDER] = folders.ids
            # Receiving made the handovers; they go with their samples, and their audit rows go below.
            handovers = env[MODEL_SAMPLE_HANDOVER].search([("sample_id", "in", self.owned[MODEL_SAMPLE])])
            self.owned[MODEL_SAMPLE_HANDOVER] = handovers.ids
            self.owned[MODEL_CALENDAR_USER] = env[MODEL_CALENDAR_USER].search([("user_id", "in", user_ids)]).ids
            messages = Domain.OR(
                [Domain("model", "=", model) & Domain("res_id", "in", ids) for model, ids in self.owned.items() if ids]
                + [
                    Domain("author_id", "in", self.owned[MODEL_RES_PARTNER]),
                    Domain("partner_ids", "in", self.owned[MODEL_RES_PARTNER]),
                    Domain("notification_ids.res_partner_id", "in", self.owned[MODEL_RES_PARTNER]),
                ]
            )
            self.owned[MODEL_MAIL_MESSAGE] = env[MODEL_MAIL_MESSAGE].search(messages).ids
            # These documents forbid ordinary deletion. Remove only this fixture's exact committed IDs and audit rows,
            # with the rows its own users wrote about documents already deleted, such as a cancelled booking's events.
            owned = SQL(" OR ").join(
                [
                    SQL("(document_model = %s AND document_id = ANY(%s))", model, ids)
                    for model, ids in self.owned.items()
                    if ids
                ]
                + [SQL("user_id = ANY(%s)", user_ids)]
            )
            env.cr.execute(
                SQL(
                    "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE %s)",
                    owned,
                )
            )
            env.cr.execute(SQL("DELETE FROM medilab_audit_entry WHERE %s", owned))
            # Attachments of the records, such as the people's avatars, which deleting the records with SQL would orphan.
            attachments = SQL(" OR ").join(
                SQL("(res_model = %s AND res_id = ANY(%s))", model, ids) for model, ids in self.owned.items() if ids
            )
            env.cr.execute(SQL("SELECT id FROM ir_attachment WHERE %s", attachments))
            env[MODEL_IR_ATTACHMENT].browse([row[0] for row in env.cr.fetchall()]).unlink()
            for model in (
                MODEL_TASK_REASSIGN,
                MODEL_MAIL_MESSAGE,
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
                MODEL_EMPLOYEE,
                MODEL_RESOURCE,
                MODEL_CALENDAR_USER,
                MODEL_RES_USERS,
                MODEL_RES_PARTNER,
                MODEL_DEPARTMENT,
            ):
                if ids := self.owned.get(model):
                    env.cr.execute(SQL("DELETE FROM %s WHERE id = ANY(%s)", SQL.identifier(env[model]._table), ids))

        self.committed(remove)

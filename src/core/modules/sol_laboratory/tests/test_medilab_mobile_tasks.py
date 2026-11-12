from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from .task_case import TaskCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    IDEMPOTENCY_CONFLICT,
    INVALID_KEY,
    INVALID_REQUEST,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.medilab_mobile import ACTION_REFUSED, ALREADY_CLAIMED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_TASK

# The domains of the web's My Tasks, Finished Tasks and Awaiting Tasks.
WEB_OPEN = [("is_mine", "=", True), ("status", "in", ("assigned", "in_progress"))]
WEB_FINISHED = [("is_mine", "=", True), ("status", "=", "done")]
WEB_QUEUE = [("in_my_queue", "=", True)]


@tagged("post_install", "-at_install")
class TestMedilabMobileTasks(LaboratoryApiCase, TaskCase):
    """The day, the to-do list, the queues and the task actions of people signed in on Medilab Mobile: a chemist and a
    second chemist, a microbiologist, and the head of Chemistry, who creates and assigns its tasks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head = cls.create_person(
            "Do Thi Giang",
            cls.chemistry,
            "giang.do",
            permissions=[
                "task.read.own_department",
                "task.create.own_department",
                "task.edit.own_department",
                "person.read.own_department",
            ],
        )
        cls.second_chemist = cls.create_person("Pham Thi Dung", cls.chemistry, "dung.pham")
        for person in (cls.chemist, cls.second_chemist, cls.microbiologist, cls.head):
            person.user_id.password = PASSWORD

    def setUp(self):
        super().setUp()
        self.keys = {}

    def key_of(self, person):
        if person not in self.keys:
            self.keys[person] = self.signed_in_key(
                person.user_id, f"phone-{person.id}", name="Pixel 8", platform="android"
            )
        return self.keys[person]

    def on_phone(self, person, method, path, body=None, headers=None):
        return self.api(method, path, body, key=self.key_of(person), headers=headers)

    def answered(self, response, status=200):
        self.assertEqual(response.status_code, status, response.text)
        return response.json() if response.content else None

    def ids(self, tasks):
        return [task["id"] for task in tasks]

    def web(self, person, domain, order=None):
        """The tasks of the web's list as the person sees it."""
        return self.as_person(self.tasks, person).search(domain, order=order).ids

    # The day and the lists

    def test_the_open_list_shows_the_web_open_tasks_soonest_deadline_first(self):
        now = fields.Datetime.now()
        later = self.create_by_hand(self.chemist, deadline=now + timedelta(days=3))
        sooner = self.create_by_hand(self.chemist, deadline=now + timedelta(hours=2))
        overdue = self.create_by_hand(self.chemist, deadline=now - timedelta(days=1))
        started = self.create_by_hand(self.chemist, deadline=now + timedelta(days=1), status="in_progress")
        self.create_by_hand(self.chemist, status="done", done_at=now)
        self.create_by_hand(self.chemist, status="cancelled")
        self.create_by_hand(self.second_chemist)

        listed = self.answered(self.on_phone(self.chemist, "GET", "/tasks?list=open"))

        self.assertEqual(self.ids(listed["tasks"]), [overdue.id, sooner.id, started.id, later.id])
        self.assertEqual(self.ids(listed["tasks"]), self.web(self.chemist, WEB_OPEN))
        self.assertIsNone(listed["next_after"])
        self.assertEqual(listed["tasks"][0]["assignee"], self.chemist.name)

    def test_the_lists_page_through_the_tasks(self):
        tasks = [self.create_by_hand(self.chemist, deadline=self.tomorrow + timedelta(hours=hour)) for hour in range(3)]

        first = self.answered(self.on_phone(self.chemist, "GET", "/tasks?list=open&limit=2"))
        second = self.answered(
            self.on_phone(self.chemist, "GET", f"/tasks?list=open&limit=2&after={first['next_after']}")
        )

        self.assertEqual(self.ids(first["tasks"] + second["tasks"]), [task.id for task in tasks])
        self.assertIsNone(second["next_after"])
        self.assertApiRefused(INVALID_REQUEST, self.on_phone(self.chemist, "GET", "/tasks?list=all"))
        self.assertApiRefused(INVALID_REQUEST, self.on_phone(self.chemist, "GET", "/tasks"))

    def test_the_finished_list_and_the_queue_are_the_web_ones(self):
        now = fields.Datetime.now()
        older = self.create_by_hand(self.chemist, status="done", done_at=now - timedelta(days=2))
        newer = self.create_by_hand(self.chemist, status="done", done_at=now - timedelta(hours=1))
        queued = self.receive_sample(self.chemistry)
        self.receive_sample(self.microbiology)

        finished = self.answered(self.on_phone(self.chemist, "GET", "/tasks?list=finished"))
        queue = self.answered(self.on_phone(self.chemist, "GET", "/tasks?list=queue"))

        self.assertEqual(self.ids(finished["tasks"]), [newer.id, older.id])
        self.assertEqual(self.ids(queue["tasks"]), [queued.id])
        self.assertEqual(self.ids(queue["tasks"]), self.web(self.chemist, WEB_QUEUE))
        self.assertEqual(set(self.ids(finished["tasks"])), set(self.web(self.chemist, WEB_FINISHED)))

    def test_the_day_is_the_one_the_tasks_app_opens_on(self):
        self.chemist.user_id.tz = "Asia/Ho_Chi_Minh"
        overdue = self.create_by_hand(self.chemist, deadline=fields.Datetime.now() - timedelta(hours=1))
        queued = self.receive_sample(self.chemistry)

        day = self.answered(self.on_phone(self.chemist, "GET", "/tasks/today"))
        web = self.as_person(self.tasks, self.chemist).get_dashboard_data()

        self.assertEqual(day["person"], self.chemist.name)
        for count in ("open_count", "overdue_count", "due_today_count", "finished_count", "claimable_count"):
            self.assertEqual(day[count], web[count], count)
        self.assertEqual(self.ids(day["next_up"]), [overdue.id])
        self.assertEqual(self.ids(day["claimable"]), [queued.id])
        self.assertTrue(day["day_start"].endswith("+00:00"))

    # A task and its actions

    def test_a_task_gives_the_actions_the_web_shows_the_person(self):
        queued = self.receive_sample(self.chemistry)
        mine = self.create_by_hand(self.chemist, department_id=self.chemistry.id)

        as_chemist = self.answered(self.on_phone(self.chemist, "GET", f"/tasks/{queued.id}"))
        own = self.answered(self.on_phone(self.chemist, "GET", f"/tasks/{mine.id}"))
        as_head = self.answered(self.on_phone(self.head, "GET", f"/tasks/{mine.id}"))

        self.assertEqual(as_chemist["actions"], {"claim": True, "start": False, "done": False, "assign": False})
        self.assertEqual(own["actions"], {"claim": False, "start": True, "done": True, "assign": False})
        self.assertEqual(as_head["actions"], {"claim": False, "start": False, "done": False, "assign": True})
        self.assertEqual(as_chemist["document"]["screen"], "web")
        self.assertIsNone(own["document"])

    def test_a_task_the_person_may_not_read_is_not_found(self):
        other = self.create_by_hand(self.microbiologist)

        self.assertApiRefused(NOT_FOUND, self.on_phone(self.chemist, "GET", f"/tasks/{other.id}"))
        self.assertApiRefused(NOT_FOUND, self.on_phone(self.chemist, "POST", f"/tasks/{other.id}/start"))
        self.assertApiRefused(NOT_FOUND, self.on_phone(self.chemist, "GET", "/tasks/999999999"))

    def test_the_second_person_to_claim_a_task_is_told_it_is_already_claimed(self):
        task = self.receive_sample(self.chemistry)

        claimed = self.answered(self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/claim"))
        refused = self.on_phone(self.second_chemist, "POST", f"/tasks/{task.id}/claim")

        self.assertEqual((claimed["status"], claimed["assignee"]), ("assigned", self.chemist.name))
        self.assertApiRefused(ALREADY_CLAIMED, refused)
        self.assertEqual(task.assignee_id, self.chemist)
        self.assertIn(self.chemist.id, self.as_person(self.tasks, self.chemist).search(WEB_OPEN).assignee_id.ids)

    def test_a_claim_while_someone_else_is_claiming_the_task_is_told_it_is_already_claimed(self):
        task = self.receive_sample(self.chemistry)
        tasks = type(self.env[MODEL_TASK])

        # Another request holds the task's row while it claims it.
        with patch.object(tasks, "try_lock_for_update", lambda records: records.browse()):
            refused = self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/claim")

        self.assertApiRefused(ALREADY_CLAIMED, refused)
        self.assertFalse(task.assignee_id)

    def test_a_task_outside_the_person_queues_cannot_be_claimed(self):
        task = self.receive_sample(self.microbiology)

        self.assertApiRefused(ACTION_REFUSED, self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/claim"))
        self.assertFalse(task.assignee_id)

    def test_the_assignee_starts_a_task_and_marks_one_created_by_hand_done(self):
        task = self.create_by_hand(self.chemist)

        started = self.answered(self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/start"))
        done = self.answered(self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/done"))

        self.assertEqual((started["status"], done["status"]), ("in_progress", "done"))
        self.assertTrue(done["done_at"])
        self.assertApiRefused(ACTION_REFUSED, self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/start"))

    def test_a_task_the_system_closes_cannot_be_marked_done(self):
        task = self.receive_sample(self.chemistry)
        self.answered(self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/claim"))

        refused = self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/done")

        self.assertApiRefused(ACTION_REFUSED, refused)
        self.assertIn(task.name, refused.json()["error"]["message"])
        self.assertEqual(task.status, "assigned")

    # Managing tasks

    def test_the_head_assigns_a_waiting_task_and_a_reassignment_needs_a_reason(self):
        task = self.receive_sample(self.chemistry)

        assigned = self.answered(
            self.on_phone(self.head, "POST", f"/tasks/{task.id}/assign", {"assignee_id": self.chemist.id})
        )
        self.assertEqual((assigned["assignee"], assigned["status"]), (self.chemist.name, "assigned"))

        refused = self.on_phone(self.head, "POST", f"/tasks/{task.id}/assign", {"assignee_id": self.second_chemist.id})
        self.assertApiRefused(ACTION_REFUSED, refused)
        blank = self.on_phone(
            self.head, "POST", f"/tasks/{task.id}/assign", {"assignee_id": self.second_chemist.id, "reason": "  "}
        )
        self.assertApiRefused(ACTION_REFUSED, blank)
        self.assertEqual(task.assignee_id, self.chemist)

        moved = self.answered(
            self.on_phone(
                self.head,
                "POST",
                f"/tasks/{task.id}/assign",
                {"assignee_id": self.second_chemist.id, "reason": "An is on leave"},
            )
        )
        self.assertEqual((moved["assignee"], moved["reassign_reason"]), (self.second_chemist.name, "An is on leave"))
        self.assertEqual(task.assigned_by_id, self.head)

    def test_moving_a_task_to_another_department_needs_a_reason(self):
        task = self.receive_sample(self.chemistry)
        path = f"/tasks/{task.id}/assign"

        self.assertApiRefused(
            ACTION_REFUSED, self.on_phone(self.head, "POST", path, {"department_id": self.microbiology.id})
        )
        moved = self.on_phone(
            self.head, "POST", path, {"department_id": self.microbiology.id, "reason": "Microbiology"}
        )

        self.assertIn(moved.status_code, (200, 204), moved.text)
        self.assertEqual((task.department_id, task.reassign_reason), (self.microbiology, "Microbiology"))

    def test_a_person_without_the_task_permissions_neither_assigns_nor_creates(self):
        task = self.receive_sample(self.chemistry)
        new = {"name": "Call the customer", "assignee_id": self.chemist.id, "deadline": "2026-12-01T09:00:00+07:00"}

        me = self.answered(self.on_phone(self.chemist, "GET", "/me"))
        self.assertEqual(me["can"], {"create_tasks": False, "assign_tasks": False})
        self.assertApiRefused(
            PERMISSION_DENIED,
            self.on_phone(self.chemist, "POST", f"/tasks/{task.id}/assign", {"assignee_id": self.chemist.id}),
        )
        self.assertApiRefused(PERMISSION_DENIED, self.on_phone(self.chemist, "POST", "/tasks", new))
        self.assertApiRefused(PERMISSION_DENIED, self.on_phone(self.chemist, "GET", "/tasks/assignees"))
        self.assertFalse(task.assignee_id)

    def test_the_head_creates_a_task_by_hand_once_per_idempotency_key(self):
        new = {
            "name": "Calibrate the pH meter",
            "note": "Use the pH 4 and pH 7 buffers.",
            "assignee_id": self.chemist.id,
            "deadline": "2026-12-01T09:00:00+07:00",
        }
        headers = {"Idempotency-Key": "task-1"}

        created = self.answered(self.on_phone(self.head, "POST", "/tasks", new, headers=headers))
        again = self.answered(self.on_phone(self.head, "POST", "/tasks", new, headers=headers))
        conflict = self.on_phone(self.head, "POST", "/tasks", {**new, "name": "Another"}, headers=headers)

        task = self.tasks.browse(created["id"])
        self.assertEqual(again["id"], task.id)
        self.assertApiRefused(IDEMPOTENCY_CONFLICT, conflict)
        self.assertEqual(self.tasks.search_count([("name", "=", "Calibrate the pH meter")]), 1)
        self.assertEqual(
            (task.type_id, task.assignee_id, task.department_id, task.assigned_by_id, task.status),
            (self.general, self.chemist, self.chemistry, self.head, "assigned"),
        )
        self.assertEqual(task.deadline, fields.Datetime.to_datetime("2026-12-01 02:00:00"))
        self.assertFalse(task.document_id)
        phone = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", f"phone-{self.head.id}")])
        self.assertEqual(task.created_by_device_id, phone)
        self.assertIn(task.id, self.web(self.chemist, WEB_OPEN))

    def test_the_head_finds_people_and_departments_to_assign_to(self):
        me = self.answered(self.on_phone(self.head, "GET", "/me"))
        found = self.answered(self.on_phone(self.head, "GET", "/tasks/assignees?q=Pham"))

        self.assertEqual(me["can"], {"create_tasks": True, "assign_tasks": True})
        self.assertEqual((me["login"], me["department"]), ("giang.do", self.chemistry.name))
        self.assertEqual(
            found["people"],
            [{"id": self.second_chemist.id, "name": self.second_chemist.name, "department": self.chemistry.name}],
        )
        departments = self.answered(self.on_phone(self.head, "GET", "/tasks/assignees?q=Micro"))["departments"]
        self.assertEqual(departments, [{"id": self.microbiology.id, "name": self.microbiology.name}])

    def test_a_revoked_phone_is_refused(self):
        key = self.key_of(self.chemist)
        self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", f"phone-{self.chemist.id}")]).action_revoke()

        self.assertApiRefused(INVALID_KEY, self.api("GET", "/tasks?list=open", key=key))
        self.assertEqual(self.env[MODEL_TASK].search_count([("assignee_id", "=", self.chemist.id)]), 0)

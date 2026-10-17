from freezegun import freeze_time

from odoo.tests import tagged

from .scheduling_case import MONDAY
from .task_link_case import TaskLinkCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import (
    LINK_CHANGED,
    LINK_NOT_OF_TYPE,
    LINK_UNRECORDED,
    TESTING_ACTION,
)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestLegacyTaskLinks(TaskLinkCase):
    """Tasks stored before links were locked, next to the genuine testing task of the same test."""

    def setUp(self):
        super().setUp()
        (self.fast | self.slow).status = "under_repair"
        self.genuine = self.testing_task(self.test)

    def forget_history(self, task):
        """Remove the task's audit entries, as for a task older than the trail or whose entries were archived."""
        self.env.flush_all()
        self.env.cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN "
            "(SELECT id FROM medilab_audit_entry WHERE document_model = %s AND document_id = %s)",
            (MODEL_TASK, task.id),
        )
        self.env.cr.execute(
            "DELETE FROM medilab_audit_entry WHERE document_model = %s AND document_id = %s", (MODEL_TASK, task.id)
        )
        self.env.invalidate_all()

    def legacy_tasks(self):
        """A task linked by hand, one then changed to the testing type, and one changed so long ago its history is gone."""
        linked = self.legacy_task(self.department)
        retyped = self.legacy_task(self.microbiology, retype=True)
        unrecorded = self.legacy_task(self.microbiology, retype=True)
        self.forget_history(unrecorded)
        return linked, retyped, unrecorded

    def assert_reaches_nothing(self, task):
        forged = self.as_person(task, self.planner)

        self.assertFalse(forged.method_step_ids)
        self.assertEqual(forged.action_assign_sample()["context"]["active_ids"], [task.id])
        forged.write({"assignee_id": self.tester.id, "reassign_reason": "Cuong is free."})
        self.assertEqual([self.test.status, self.test.outsourcing_suggested], ["waiting", False])
        self.assertEqual(self.test._tested_by(), self.department)
        self.assertEqual(self.test._testing_task(), self.genuine)
        self.assertEqual(self.env[MODEL_TASK]._system_tasks_of(self.test, TESTING_ACTION), self.genuine)

    def test_a_legacy_task_reaches_nothing_of_the_test(self):
        legacy = self.legacy_tasks()
        for task in legacy:
            with self.subTest(type=task.type_id.code, recorded=bool(self.history(task))):
                self.assert_reaches_nothing(task)
        self.env[MODEL_TASK]._close_for_document(self.test, TESTING_ACTION)
        self.assertEqual(
            [self.genuine.status, *(task.status for task in legacy)], ["done", "assigned", "assigned", "assigned"]
        )

    def test_the_genuine_testing_task_still_drives_its_test(self):
        self.legacy_tasks()
        self.genuine.write({"assignee_id": self.tester.id})

        self.assertEqual(self.test.status, "assigned")
        self.assertEqual(
            self.as_person(self.genuine, self.tester).method_step_ids.mapped("instruction"), ["Weigh the sample."]
        )
        self.assertEqual(self.test._tested_by(), self.department)

    def test_the_trail_verifies_only_tasks_it_shows_unchanged_since_created(self):
        recorded = self.testing_task(self.new_test())
        unrecorded = self.testing_task(self.new_test())
        (recorded | unrecorded | self.genuine).write({"linked_by_system": False})
        self.forget_history(unrecorded)
        linked, retyped, forgotten = self.legacy_tasks()
        ours = recorded | unrecorded | self.genuine | linked | retyped | forgotten

        verified = self.env[MODEL_TASK]._verify_links_from_history()

        self.assertEqual(verified & ours, recorded | self.genuine)
        self.assertEqual(
            {
                row["task_id"]: row["finding"]
                for row in self.env[MODEL_TASK]._link_review()
                if row["task_id"] in ours.ids
            },
            {
                unrecorded.id: LINK_UNRECORDED,
                linked.id: LINK_NOT_OF_TYPE,
                retyped.id: LINK_CHANGED,
                forgotten.id: LINK_UNRECORDED,
            },
        )
        self.assertFalse((unrecorded | linked | retyped | forgotten).filtered("linked_by_system"))

    def test_the_review_names_the_test_each_task_reaches(self):
        linked, _retyped, _forgotten = self.legacy_tasks()

        rows = {row["task_id"]: row for row in self.env[MODEL_TASK]._link_review()}

        self.assertEqual(
            [rows[linked.id][key] for key in ("type", "status", "document_model", "document_id", "document", "sample")],
            ["general", "assigned", "medilab.sample.test", self.test.id, self.test.display_name, self.sample.code],
        )

    def test_an_administrator_confirms_an_unrecorded_task_on_the_record(self):
        task = self.testing_task(self.new_test())
        task.write({"linked_by_system": False})
        self.forget_history(task)
        test = self.env["medilab.sample.test"].browse(task.document_id)
        self.assertFalse(test._tested_by())

        task.write({"linked_by_system": True})

        self.assertEqual(test._tested_by(), self.department)
        self.assertIn("linked_by_system", self.history(task, "edit").change_ids.mapped("field_name"))

    def test_changing_a_link_ends_the_trust_whatever_the_call_says(self):
        other = self.new_test()
        other.parameter_method_id = self.pair
        repointed = self.testing_task(self.new_test())
        retyped = self.legacy_task(self.microbiology)

        repointed.write({"document_id": other.id, "linked_by_system": True})
        retyped.write({"type_id": self.testing_type.id, "action": TESTING_ACTION, "linked_by_system": True})

        self.assertEqual([repointed.linked_by_system, retyped.linked_by_system], [False, False])
        for task, test in ((repointed, other), (retyped, self.test)):
            with self.subTest(task=task.name):
                changed = self.as_person(task, self.planner)
                self.assertFalse(changed.method_step_ids)
                self.assertEqual(changed.action_assign_sample()["context"]["active_ids"], [task.id])
                changed.write({"assignee_id": self.tester.id, "reassign_reason": "Cuong is free."})
                self.assertEqual([test.status, test.outsourcing_suggested], ["waiting", False])
        self.assertFalse(other._tested_by())
        self.assertEqual(self.test._tested_by(), self.department)
        self.assertEqual(self.test._testing_task(), self.genuine)

    def test_only_a_separate_confirmation_trusts_a_changed_task_again(self):
        task = self.testing_task(self.new_test())
        test = self.env["medilab.sample.test"].browse(task.document_id)

        task.write({"document_id": test.id, "linked_by_system": True})
        self.assertFalse(task.linked_by_system)
        self.assertFalse(test._tested_by())
        task.write({"linked_by_system": True})

        self.assertTrue(task.linked_by_system)
        self.assertEqual(test._tested_by(), self.department)
        confirmations = self.history(task, "edit").change_ids.filtered(
            lambda change: change.field_name == "linked_by_system"
        )
        self.assertEqual(len(confirmations), 2)

    def test_verifying_again_changes_nothing(self):
        task = self.testing_task(self.new_test())
        task.write({"linked_by_system": False})
        self.assertIn(task, self.env[MODEL_TASK]._verify_links_from_history())
        history = self.history(task)

        self.assertNotIn(task, self.env[MODEL_TASK]._verify_links_from_history())
        self.assertEqual(self.history(task), history)
        self.assertTrue(task.linked_by_system)

    def test_link_checks_take_as_many_queries_for_many_tasks_as_for_few(self):
        few = self.legacy_task(self.department) | self.testing_task(self.new_test())
        many = few
        for _index in range(4):
            many |= self.legacy_task(self.department) | self.testing_task(self.new_test())

        for name, check in (
            ("findings", lambda tasks: tasks._link_findings()),
            ("trusted", lambda tasks: tasks.filtered_domain(tasks._testing_domain())),
            ("steps", lambda tasks: tasks.mapped("method_step_ids")),
        ):
            with self.subTest(check=name):
                self.assertEqual(self.queries(lambda: check(many)), self.queries(lambda: check(few)))

    def history(self, task, action=None):
        domain = [("document_model", "=", MODEL_TASK), ("document_id", "=", task.id)]
        return self.env[MODEL_AUDIT_ENTRY].search(domain + ([("action", "=", action)] if action else []))

    def queries(self, run):
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_log_count
        run()
        return self.env.cr.sql_log_count - before

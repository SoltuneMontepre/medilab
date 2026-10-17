# Reviewing task links

A task acts on its document with full rights, such as showing a testing method's steps or moving a sample test along as the task is assigned, only while the system linked it (`linked_by_system`). Before the upgrade to `sol_laboratory` 20.0.1.6.0, anyone who could create or edit tasks could link a task to any document or change its type. The upgrade verifies the existing tasks from the audit trail and leaves every other task untrusted. An administrator reviews those tasks before production is called secure.

The audit trail cannot clear every task. A task created before the trail existed, or whose entries the cleanup job archived, has no creation record. Missing history is not proof: such a task stays untrusted until an administrator confirms it.

## Steps

1. **Upgrade** `sol_laboratory` on the database. The upgrade log says how many tasks it verified, and lists every task that needs a review with its finding.
2. **List the tasks** without changing anything, from an Odoo shell on the database:

   ```python
   for row in env["medilab.task"]._link_review():
       print(row)
   ```

   Each row names the task, its type and status, the finding, and the document the task names, with the sample's code for a sample test.
3. **Review each task** by its finding:

   | Finding | What it means | What to do |
   | --- | --- | --- |
   | `not_of_its_type` | A task made by hand names a document or action its type does not. | Treat it as forged. It never acts on the document. Check the document for what the task could do before the upgrade, then cancel the task if it is still open. |
   | `changed_after_creation` | Someone changed the task's type, document or action after it was created. | Treat it as forged and never confirm it. Check the document, then cancel the task if it is still open. |
   | `creation_not_recorded` | The trail has no record of the task's creation. | Compare it with the archived audit files and the sample's reception. Confirm it only when it is the test's genuine testing task; otherwise cancel it. |

4. **Check the sample test** a forged task names: its status and outsourcing suggestion, which department tested it, and who signed its results. Use the History of the test, its results and the task. Correct the work through the documents' own actions, such as a change request on a result.
5. **Give the test a testing task** when it has none the system trusts and its work is not finished: open one in the department that tests it, from an Odoo shell, with `test._open_testing_task(department)`.
6. **Confirm or cancel** from an Odoo shell, so the change is recorded in the audit trail under the administrator:
   - Confirm a genuine task: `task.write({"linked_by_system": True})`.
   - Cancel a task: `task.write({"status": "cancelled"})`.
7. **Run the list again.** The review is done when every listed task is cancelled, confirmed, or knowingly left untrusted.

## Rules

- Never delete a task or an audit entry, and never change a task's type, document or action. The task and its history are the evidence.
- Never confirm a task found `not_of_its_type` or `changed_after_creation`.
- Confirm a task in a call of its own. A change to a task's type, document or action always leaves it untrusted, even when the same call confirms it.
- A testing task left untrusted does not move its test along, does not show the method's steps, is not closed by the system, and does not name the department that tested the test. Until the test has a trusted testing task, results waiting for that department's signature cannot be signed.
- Production is not called secure until the review is done.

## Related documents

- [Shared requirements: SH-10 Tasks and to-do list](../functional/shared.md#sh-10-tasks-and-to-do-list)
- [Audit trail](../specs/audit-trail.md)

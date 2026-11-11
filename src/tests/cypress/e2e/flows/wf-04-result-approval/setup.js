import { callAs } from "../../../support/odoo";
import { testingTasks as sampleTestingTasks } from "../wf-03-testing-scheduling/setup";
import { TESTER, assignedTest } from "../wf-05-outsourced-testing/setup";

export { TESTER, assignedTest };

// The testing tasks of a sample test, oldest first.
export function testingTasks(test) {
  return sampleTestingTasks({ tests: [test] }).then((tasks) => Cypress._.sortBy(tasks, "id"));
}

// The results of a sample test, the latest entered first.
export function results(test) {
  return callAs(TESTER, "medilab.test.result", "search_read", [[["sample_test_id", "=", test.id]]], {
    fields: ["status", "is_reported"],
  }).then((rows) => rows.map((row) => ({ ...row, model: "medilab.test.result" })));
}

// An in-house sample test assigned to the tester, whose result the tester entered and sent for approval.
export function sentResult() {
  return assignedTest("lead", { days: 7 }).then((test) =>
    callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: test.id, value: 0.008 }]).then((id) =>
      callAs(TESTER, "medilab.test.result", "action_sign", [[id]]).then(() => ({
        test,
        result: { model: "medilab.test.result", id },
      })),
    ),
  );
}

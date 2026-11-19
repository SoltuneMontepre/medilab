import { callAs, refAs } from "../../../support/odoo";
import { helper } from "../../../support/steps";

export const STAFF = "demo.sample_delivery_staff";
export const LAB_HEAD = "demo.lab_head";
export const HEAD = "demo.head_of_department";
const TESTER = "demo.tester";

export const PARAMETERS = {
  lead: "sol_demo.demo_test_parameter_lead",
  ph: "sol_demo.demo_test_parameter_ph",
};

// A passing value of each parameter, within QCVN 6-1.
const PASSING = { [PARAMETERS.lead]: 0.004, [PARAMETERS.ph]: 7.2 };

// Resolves external IDs as the administrator into `{ xmlId: id }`.
function refs(xmlIds) {
  const ids = {};
  for (const xmlId of xmlIds) {
    refAs("demo.administrator", xmlId).then(({ id }) => (ids[xmlId] = id));
  }
  return cy.wrap(ids);
}

// The open testing tasks of the sample tests.
export const testingTasks = (tests) =>
  callAs(HEAD, "medilab.task", "search", [
    [
      ["document_model", "=", "medilab.sample.test"],
      ["document_id", "in", tests],
      ["status", "not in", ["done", "cancelled"]],
    ],
  ]);

// The head of department gives the tasks to the tester through the Reassign dialog.
export const assignToTester = helper("assignToTester", function assignToTester(tasks) {
  const context = { active_ids: tasks };
  return refAs(HEAD, "sol_demo.demo_person_tester").then((tester) =>
    callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: tester.id }], { context }).then((wizard) =>
      callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
    ),
  );
});

// Confirms a test request, receives its samples and has the head of department give their testing tasks to the tester.
export const receiveRequest = helper("receiveRequest", function receiveRequest(requestId) {
  callAs(STAFF, "medilab.test.request", "action_confirm", [[requestId]]);
  return callAs(STAFF, "medilab.test.request", "read", [[requestId], ["sample_ids"]])
    .then(([request]) => {
      callAs(STAFF, "medilab.sample", "action_receive", [request.sample_ids, "2 bottles", "good"]);
      return callAs(STAFF, "medilab.sample", "read", [request.sample_ids, ["test_ids"]]);
    })
    .then((samples) => {
      const tests = samples.flatMap((sample) => sample.test_ids);
      return testingTasks(tests).then((tasks) => assignToTester(tasks).then(() => tests));
    });
});

// The tester enters and signs a passing result of each test; the head of department approves it.
export const approveTests = helper("approveTests", function approveTests(testIds, cancelled = []) {
  return refs(Object.values(PARAMETERS)).then((ids) =>
    callAs(TESTER, "medilab.sample.test", "read", [testIds, ["parameter_id"]]).then((tests) => {
      for (const test of tests) {
        const parameter = Object.keys(PASSING).find((xmlId) => ids[xmlId] === test.parameter_id[0]);
        if (cancelled.includes(test.id)) {
          callAs(HEAD, "medilab.sample.test", "action_cancel", [[test.id], "Too little sample was left after the lead digestion."]);
          continue;
        }
        callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: test.id, value: PASSING[parameter], conclusion: "pass" }]).then(
          (result) => {
            callAs(TESTER, "medilab.test.result", "action_sign", [[result]]);
            callAs(HEAD, "medilab.test.result", "action_sign", [[result]]);
          },
        );
      }
    }),
  );
});

// A test request of Nước Uống Sạch whose results are all approved, with its draft report, as `{ request, report }`.
// `samples` lists the parameters of each bottled water sample; `cancel` names parameters whose test the head of
// department cancels instead; `values` sets fields of the request, such as its report language. The browser tests
// never sign a new report: signing needs its PDF prepared through ONLYOFFICE.
export const draftReport = helper("draftReport", function draftReport({ samples = [[PARAMETERS.lead, PARAMETERS.ph]], cancel = [], ...values } = {}) {
  return refs([
    "sol_demo.demo_customer_nuoc_sach",
    "sol_demo.demo_sample_type_bottled_water",
    "sol_demo.demo_regulation_qcvn_6_1",
    ...Object.values(PARAMETERS),
  ])
    .then((ids) =>
      callAs(STAFF, "medilab.test.request", "create", [
        {
          customer_id: ids["sol_demo.demo_customer_nuoc_sach"],
          sample_ids: samples.map((parameters, index) => [
            0,
            0,
            {
              customer_sample_name: `Nước đóng chai ${index + 1}`,
              sample_type_id: ids["sol_demo.demo_sample_type_bottled_water"],
              physical_state: "liquid",
              regulation_id: ids["sol_demo.demo_regulation_qcvn_6_1"],
              test_ids: parameters.map((xmlId) => [0, 0, { parameter_id: ids[xmlId] }]),
            },
          ]),
          ...values,
        },
      ]).then((requestId) =>
        receiveRequest(requestId).then((tests) =>
          callAs(HEAD, "medilab.sample.test", "read", [tests, ["parameter_id"]]).then((read) => {
            const cancelled = read.filter((test) => cancel.some((xmlId) => ids[xmlId] === test.parameter_id[0])).map((test) => test.id);
            return approveTests(tests, cancelled).then(() => requestId);
          }),
        ),
      ),
    )
    .then((requestId) =>
      callAs(LAB_HEAD, "medilab.test.report", "search", [[["request_id", "=", requestId]]]).then(([reportId]) => ({
        request: { model: "medilab.test.request", id: requestId },
        report: { model: "medilab.test.report", id: reportId },
      })),
    );
});

export const ADMIN = "demo.administrator";

export const REPORT = "medilab.test.report";

// The demo's issued reports: in English and delivered by e-mail, in Vietnamese and digitally signed for delivery by
// post, and bilingual as the replacement of a report delivered in person. A new report is never issued in the browser
// tests, as its PDF is prepared through ONLYOFFICE.
export const BY_EMAIL = "sol_demo.demo_test_report_by_email";
export const BY_POST = "sol_demo.demo_test_report_by_post";
export const REISSUED = "sol_demo.demo_test_report_reissued";

// The body of the rendered report, as the signed-in user prints it.
export const reportHtml = (report) => cy.request(`/report/html/sol_laboratory.report_test_report/${report.id}`).then(({ body }) => body.split("<main")[1]);

// Demo people's names, in the order of their external IDs.
export const personNames = (...xmlIds) =>
  callAs(
    ADMIN,
    "ir.model.data",
    "search_read",
    [
      [
        ["module", "=", "sol_demo"],
        ["name", "in", xmlIds.map((xmlId) => xmlId.split(".")[1])],
      ],
    ],
    {
      fields: ["name", "res_id"],
    },
  ).then((rows) =>
    callAs(ADMIN, "medilab.person", "read", [xmlIds.map((xmlId) => rows.find((row) => `sol_demo.${row.name}` === xmlId).res_id), ["name"]]).then(
      (people) => people.map((person) => person.name),
    ),
  );

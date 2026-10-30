import { callAs, portalPostAs, refAs } from "../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
const HEAD = "demo.head_of_department";
export const TESTER = "demo.tester";
const SUBCONTRACTOR = "demo.subcontractor";
export const ADMINISTRATOR = "demo.administrator";

// Parameters that sol_demo seeds with a subcontracted way of testing: lead by Northern Testing, whose person signs in
// as demo.subcontractor, and chlorpyrifos by Southern Micro. Both are tested in-house by Chemistry.
export const PARAMETERS = {
  lead: {
    parameter: "sol_demo.demo_test_parameter_lead",
    way: "sol_demo.demo_parameter_method_lead_subcontracted",
    sampleType: "sol_demo.demo_sample_type_bottled_water",
    state: "liquid",
  },
  chlorpyrifos: {
    parameter: "sol_demo.demo_test_parameter_chlorpyrifos",
    way: "sol_demo.demo_parameter_method_chlorpyrifos_ug",
    sampleType: "sol_demo.demo_sample_type_cabbage",
    state: "solid",
  },
};

// The subcontractor sol_demo seeds with an expired accreditation.
export const EXPIRED_SUBCONTRACTOR = "sol_demo.demo_subcontractor_coastal_analytics";

// The subcontractor sol_demo seeds archived, which an external ID does not resolve to.
export function archivedSubcontractor() {
  return callAs(ADMINISTRATOR, "medilab.subcontractor", "search", [
    [
      ["active", "=", false],
      ["accreditation_number", "=", "VILAS 404"],
    ],
  ]).then((ids) => {
    expect(ids, "archived subcontractor").to.have.length(1);
    return { model: "medilab.subcontractor", id: ids[0] };
  });
}

// Today's date plus some days, as Odoo stores a date.
export function inDays(days) {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

// The subcontractor of a parameter's subcontracted way of testing, as the head of department reads it.
function subcontractorOf(kind) {
  return refAs(HEAD, PARAMETERS[kind].way).then(({ id }) =>
    callAs(HEAD, "medilab.parameter.method", "read", [[id], ["subcontractor_id"]]).then(([way]) => way.subcontractor_id[0]),
  );
}

// The head of department cancels the subcontractor's draft dispatches, which a test outsourced next would otherwise
// join.
export function clearDrafts(kind = "lead") {
  return subcontractorOf(kind)
    .then((id) =>
      callAs(HEAD, "medilab.subcontract.dispatch", "search", [
        [
          ["subcontractor_id", "=", id],
          ["status", "=", "draft"],
        ],
      ]),
    )
    .then((ids) => ids.length && callAs(HEAD, "medilab.subcontract.dispatch", "action_cancel", [ids]));
}

// A sample test of a received sample whose testing task the head of department assigned to the tester. Its results
// are promised `days` from today: with none, its due date has passed, so no machine can finish it and the scheduler
// suggests outsourcing it.
export function assignedTest(kind = "lead", { days = 0 } = {}) {
  const { parameter, sampleType, state } = PARAMETERS[kind];
  const test = { model: "medilab.sample.test", kind };
  const ids = {};
  refAs(RECEPTION, "sol_demo.demo_customer_green_farm").then(({ id }) => (ids.customer = id));
  refAs(RECEPTION, sampleType).then(({ id }) => (ids.sampleType = id));
  refAs(RECEPTION, parameter).then(({ id }) => (ids.parameter = id));
  refAs(HEAD, "sol_demo.demo_person_tester").then(({ id }) => (ids.tester = id));
  cy.then(() =>
    callAs(RECEPTION, "medilab.test.request", "create", [
      {
        customer_id: ids.customer,
        expected_date: inDays(days),
        sample_ids: [
          [
            0,
            0,
            {
              customer_sample_name: `Mẫu gửi thầu phụ ${Date.now()}`,
              sample_type_id: ids.sampleType,
              physical_state: state,
              test_ids: [[0, 0, { parameter_id: ids.parameter }]],
            },
          ],
        ],
      },
    ]),
  )
    .then((requestId) => {
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[requestId]]);
      callAs(RECEPTION, "medilab.test.request", "read", [[requestId], ["customer_id"]]).then(
        ([request]) => (test.customerName = request.customer_id[1]),
      );
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", requestId]]], {
        fields: ["code", "customer_sample_name", "test_ids"],
      });
    })
    .then(([sample]) => {
      Object.assign(test, { id: sample.test_ids[0], code: sample.code, sampleName: sample.customer_sample_name });
      callAs(RECEPTION, "medilab.sample", "action_receive", [[sample.id], "1 chai", "good"]);
      return callAs(ADMINISTRATOR, "medilab.task", "search", [
        [
          ["document_model", "=", test.model],
          ["document_id", "=", test.id],
        ],
      ]);
    })
    .then((tasks) => {
      const context = { active_ids: tasks };
      return callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: ids.tester }], { context }).then((wizard) =>
        callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
      );
    });
  return cy.then(() => test);
}

// A sample test the scheduler suggests outsourcing.
export function suggestedTest(kind = "lead") {
  return assignedTest(kind).then((test) =>
    callAs(HEAD, "medilab.sample.test", "read", [[test.id], ["outsourcing_suggested"]]).then(([read]) => {
      expect(read.outsourcing_suggested, "outsourcing suggested").to.be.true;
      return test;
    }),
  );
}

// The outsource dialog of a sample test as the head of department fills it, through the parameter's subcontracted
// way of testing, which the dialog offers first.
export function outsourceDialog(test, values = {}) {
  return refAs(HEAD, PARAMETERS[test.kind].way).then((way) =>
    callAs(HEAD, "medilab.sample.test.outsource", "create", [{ sample_test_id: test.id, parameter_method_id: way.id, ...values }]),
  );
}

// The head of department accepts the suggestion through the outsource dialog; the test waits in a draft dispatch of
// its own.
export function outsourcedTest(kind = "lead") {
  clearDrafts(kind);
  return suggestedTest(kind).then((test) =>
    outsourceDialog(test)
      .then((wizard) => callAs(HEAD, "medilab.sample.test.outsource", "action_outsource", [[wizard]]))
      .then((action) =>
        callAs(HEAD, "medilab.subcontract.dispatch", "read", [[action.res_id], ["code"]]).then(([read]) => ({
          test,
          dispatch: { model: "medilab.subcontract.dispatch", id: action.res_id, code: read.code },
        })),
      ),
  );
}

// The head of department sends the dispatch of an outsourced test with sample delivery staff, its results expected in
// a week.
export function sentDispatch(kind = "lead") {
  return outsourcedTest(kind).then(({ test, dispatch }) =>
    refAs(HEAD, "sol_demo.demo_person_sample_delivery_staff").then((courier) => {
      callAs(HEAD, "medilab.subcontract.dispatch", "write", [[dispatch.id], { courier_id: courier.id, expected_date: inDays(7) }]);
      return callAs(HEAD, "medilab.subcontract.dispatch", "action_send", [[dispatch.id]]).then(() => ({ test, dispatch }));
    }),
  );
}

// The reported result of a sample test, as the head of department reads it.
export function reportedResult(test) {
  return callAs(
    HEAD,
    "medilab.test.result",
    "search_read",
    [
      [
        ["sample_test_id", "=", test.id],
        ["is_reported", "=", true],
      ],
    ],
    { fields: ["attempt", "status", "entered_by_id", "value"] },
  ).then(([result]) => ({ ...result, model: "medilab.test.result" }));
}

// The subcontractor's person enters a test's result on the portal page of its dispatch.
export function subcontractorResult({ test, dispatch }, value = "4.2") {
  const page = `/my/dispatches/${dispatch.id}`;
  portalPostAs(SUBCONTRACTOR, page, `${page}/results`, { sample_test_id: test.id, value });
  return reportedResult(test);
}

// A sent dispatch whose test has the subcontractor's result, which the tester sent for approval.
export function resultAwaitingApproval(kind = "lead") {
  return sentDispatch(kind).then((sent) =>
    subcontractorResult(sent).then((result) =>
      callAs(TESTER, "medilab.test.result", "action_sign", [[result.id]]).then(() => ({ ...sent, result })),
    ),
  );
}

// A testing method and unit that sol_demo seeds, to make ways of testing with.
export function wayParts() {
  const parts = {};
  refAs(ADMINISTRATOR, "sol_demo.demo_testing_method_iso_17294_2").then(({ id }) => (parts.methodId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_measurement_unit_ug_l").then(({ id }) => (parts.unitId = id));
  return cy.then(() => parts);
}

// A heavy-metal parameter the administrator creates without ways of testing.
export function newParameter() {
  const name = `Kim loại thầu phụ ${Date.now()}`;
  return refAs(ADMINISTRATOR, "sol_demo.demo_parameter_group_heavy_metals").then((group) =>
    callAs(ADMINISTRATOR, "medilab.test.parameter", "create", [{ name, main_group_id: group.id, group_ids: [[6, 0, [group.id]]] }]).then(
      (id) => ({ model: "medilab.test.parameter", id, name }),
    ),
  );
}

// A subcontractor the administrator records, its accreditation valid for a year.
export function newSubcontractor() {
  const name = `Phòng thử nghiệm ${Date.now()}`;
  return callAs(ADMINISTRATOR, "medilab.subcontractor", "create", [
    { name, is_company: true, accreditation_number: "VILAS 909", accreditation_expiry: inDays(365) },
  ]).then((id) => ({ model: "medilab.subcontractor", id, name }));
}

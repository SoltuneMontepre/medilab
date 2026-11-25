import { callAs, refAs } from "../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
const HEAD = "demo.head_of_department";
const LAB_HEAD = "demo.lab_head";
export const ADMINISTRATOR = "demo.administrator";
export const TESTER = "demo.tester";

// What the tester measured for lead, in mg/L.
export const LEAD_VALUE = 0.008;

// The chain that signs results: the tester, then the head of department.
export const RESULT_CHAIN = "sol_demo.demo_approval_chain_test_result_signing";
// The level a test adds after the head of department's, so a result both signed is still in its process.
export const FINAL_LEVEL = "Final approval";

// A confirmed request of Nước Uống Sạch with one bottled water sample tested for the parameter, received in good
// condition and whose testing task the head of department assigned to the tester. The sample is named `name` and, when
// `regulation` gives one by its XML ID, compared with that regulation. Yields the ids of its sample test and request.
export function assignedTest(parameterId, { name, regulation } = {}) {
  const ids = {};
  refAs(RECEPTION, "sol_demo.demo_customer_nuoc_sach").then(({ id }) => (ids.customer = id));
  refAs(RECEPTION, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (ids.sampleType = id));
  if (regulation) {
    refAs(RECEPTION, regulation).then(({ id }) => (ids.regulation = id));
  }
  refAs(HEAD, "sol_demo.demo_person_tester").then(({ id }) => (ids.tester = id));
  return cy
    .then(() =>
      callAs(RECEPTION, "medilab.test.request", "create", [
        {
          customer_id: ids.customer,
          sample_ids: [
            [
              0,
              0,
              {
                customer_sample_name: name,
                sample_type_id: ids.sampleType,
                physical_state: "liquid",
                regulation_id: ids.regulation || false,
                test_ids: [[0, 0, { parameter_id: parameterId }]],
              },
            ],
          ],
        },
      ]),
    )
    .then((request) => {
      ids.request = request;
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[request]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", request]]], { fields: ["test_ids"] });
    })
    .then(([sample]) => {
      ids.test = sample.test_ids[0];
      callAs(RECEPTION, "medilab.sample", "action_receive", [[sample.id], "2 chai", "good"]);
      return callAs(HEAD, "medilab.task", "search", [
        [
          ["document_model", "=", "medilab.sample.test"],
          ["document_id", "=", ids.test],
        ],
      ]);
    })
    .then((tasks) => {
      ids.tasks = tasks;
      // The Lab Head authorizes the tester for a parameter the demo data does not authorize them for.
      const authorization = [
        ["person_id", "=", ids.tester],
        ["parameter_id", "=", parameterId],
      ];
      return callAs(LAB_HEAD, "medilab.parameter.authorization", "search_count", [authorization]);
    })
    .then((count) => count || callAs(LAB_HEAD, "medilab.parameter.authorization", "create", [{ person_id: ids.tester, parameter_id: parameterId }]))
    .then(() => {
      const context = { active_ids: ids.tasks };
      return callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: ids.tester }], { context }).then((wizard) =>
        callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
      );
    })
    .then(() => ({ test: ids.test, request: ids.request }));
}

// A result the tester entered for lead and sent, which signs the chain's first level. Testing belongs to WF-03.
// Yields `{ model, id, request }`.
export function sentResult() {
  let request;
  return refAs(RECEPTION, "sol_demo.demo_test_parameter_lead")
    .then(({ id }) => assignedTest(id, { name: "Nước uống đóng chai lô 1109" }))
    .then((assigned) => {
      request = assigned.request;
      return callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: assigned.test, value: LEAD_VALUE, value_decimals: 3 }]);
    })
    .then((id) => {
      callAs(TESTER, "medilab.test.result", "action_sign", [[id]]);
      return cy.wrap({ model: "medilab.test.result", id, request });
    });
}

// The sent result once the head of department signed it, in the status `status`. Yields `{ model, id, request }`.
function headSigned(status) {
  return sentResult().then((result) => {
    callAs(HEAD, "medilab.test.result", "action_sign", [[result.id]]);
    callAs(HEAD, "medilab.test.result", "read", [[result.id], ["status"]])
      .its("0.status")
      .should("eq", status);
    return cy.wrap(result);
  });
}

// A completed result: the tester sent it and the head of department approved it. Approving belongs to WF-04.
// Yields `{ model, id, request }`.
export function approvedResult() {
  return headSigned("approved");
}

// A result still in its process: the tester sent it and the head of department signed it, and it waits for the level
// `addFinalLevel` added. Yields `{ model, id, request }`.
export function signedResult() {
  return headSigned("requested");
}

// Adds a last level, held by the role with the XML ID `role`, to the chain of results.
export function addFinalLevel(role = "sol_demo.demo_role_lab_head") {
  const ids = {};
  refAs(ADMINISTRATOR, RESULT_CHAIN).then(({ id }) => (ids.chain = id));
  refAs(ADMINISTRATOR, role).then(({ id }) => (ids.role = id));
  return cy.then(() =>
    callAs(ADMINISTRATOR, "medilab.approval.level", "create", [
      { chain_id: ids.chain, sequence: 30, name: FINAL_LEVEL, role_id: ids.role, can_reject: false },
    ]),
  );
}

// Removes the level a test added to the chain of results, which every other result is signed without; a level that
// results signed at is archived.
export function removeFinalLevel() {
  return refAs(ADMINISTRATOR, RESULT_CHAIN)
    .then(({ id }) =>
      callAs(ADMINISTRATOR, "medilab.approval.level", "search", [
        [
          ["chain_id", "=", id],
          ["name", "=", FINAL_LEVEL],
        ],
      ]),
    )
    .then((levels) => levels.length && callAs(ADMINISTRATOR, "medilab.approval.level", "unlink", [levels]));
}

// The demo report issued by email. A new report is signed only after its PDF is prepared through ONLYOFFICE, which the
// browser tests run without; issuing belongs to WF-06. Yields `{ model, id, code }`.
export function issuedReport() {
  return refAs(LAB_HEAD, "sol_demo.demo_test_report_by_email").then(({ model, id }) =>
    callAs(LAB_HEAD, model, "read", [[id], ["status", "code"]]).then(([report]) => {
      expect(report.status, "report issued").to.equal("issued");
      return { model, id, code: report.code };
    }),
  );
}

// A change request the tester raised on a result through its Request a Change dialog. Yields `{ model, id }`.
export function requestedChange(result, requestedChange, reason) {
  return callAs(TESTER, "medilab.change.request.raise", "create", [
    { document_model: result.model, document_id: result.id, requested_change: requestedChange, reason },
  ])
    .then((wizard) => callAs(TESTER, "medilab.change.request.raise", "action_raise", [[wizard]]))
    .then((action) => ({ model: "medilab.change.request", id: action.res_id }));
}

// The signatures of a document, oldest first, as the administrator reads them.
export function signatures(document) {
  return callAs(
    ADMINISTRATOR,
    "medilab.signature",
    "search_read",
    [
      [
        ["document_model", "=", document.model],
        ["document_id", "=", document.id],
      ],
    ],
    { fields: ["level_name", "decision", "withdrawn_at", "document_version"], order: "id" },
  );
}

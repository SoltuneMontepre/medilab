import { callAs, refAs } from "../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
const HEAD = "demo.head_of_department";
const LAB_HEAD = "demo.lab_head";
const STOREKEEPER = "demo.storekeeper";
export const ADMINISTRATOR = "demo.administrator";
export const TESTER = "demo.tester";

// What the tester measured for lead, in mg/L.
export const LEAD_VALUE = 0.008;

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
      return callAs(LAB_HEAD, "medilab.parameter.authorization", "search_count", [authorization]).then(
        (count) => count || callAs(LAB_HEAD, "medilab.parameter.authorization", "create", [{ person_id: ids.tester, parameter_id: parameterId }]),
      );
    })
    .then(() => {
      const context = { active_ids: ids.tasks };
      return callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: ids.tester }], { context }).then((wizard) =>
        callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
      );
    })
    .then(() => ({ test: ids.test, request: ids.request }));
}

// A completed result: the tester entered lead and sent it, and the head of department approved it. Testing and
// approving belong to WF-03 and WF-04. Yields `{ model, id, request }`.
export function approvedResult() {
  let request;
  return refAs(RECEPTION, "sol_demo.demo_test_parameter_lead")
    .then(({ id }) => assignedTest(id, { name: "Nước uống đóng chai lô 1109" }))
    .then((assigned) => {
      request = assigned.request;
      return callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: assigned.test, value: LEAD_VALUE, value_decimals: 3 }]);
    })
    .then((id) => {
      callAs(TESTER, "medilab.test.result", "action_sign", [[id]]);
      callAs(HEAD, "medilab.test.result", "action_sign", [[id]]);
      callAs(HEAD, "medilab.test.result", "read", [[id], ["status"]])
        .its("0.status")
        .should("eq", "approved");
      return cy.wrap({ model: "medilab.test.result", id, request });
    });
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

// A purchase order of sodium chloride the storekeeper sent for approval, signing the first level. Yields its id.
export function requestedOrder(quantity) {
  const ids = {};
  refAs(STOREKEEPER, "sol_demo.demo_res_partner_vietnam_chemicals").then(({ id }) => (ids.supplier = id));
  refAs(STOREKEEPER, "sol_demo.demo_hr_department_chemistry").then(({ id }) => (ids.department = id));
  refAs(STOREKEEPER, "sol_demo.demo_product_product_sodium_chloride").then(({ id }) => (ids.item = id));
  return cy
    .then(() =>
      callAs(STOREKEEPER, "purchase.order", "create", [
        {
          partner_id: ids.supplier,
          department_id: ids.department,
          order_line: [[0, 0, { product_id: ids.item, product_qty: quantity, price_unit: 380 }]],
        },
      ]),
    )
    .then((id) => {
      callAs(STOREKEEPER, "purchase.order", "action_request_approval", [[id]]);
      return cy.wrap(id);
    });
}

// A purchase order still in its process: the storekeeper requested approval and the lab head signed it, and it is
// not sent to the supplier yet. Yields `{ model, id }`.
export function signedOrder() {
  let orderId;
  return requestedOrder(2000)
    .then((id) => {
      orderId = id;
      callAs(LAB_HEAD, "purchase.order", "action_sign", [[id]]);
      return callAs(LAB_HEAD, "purchase.order", "read", [[id], ["approval_status", "state"]]);
    })
    .then(([order]) => {
      expect(order.approval_status, "order approved").to.equal("approved");
      expect(order.state, "order not sent").to.equal("draft");
      return { model: "purchase.order", id: orderId };
    });
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

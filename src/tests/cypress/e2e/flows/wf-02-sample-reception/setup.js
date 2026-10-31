import { callAs, refAs } from "../../../support/odoo";
import { orderAt } from "../wf-01-order-to-test-request/setup";

export const STAFF = "demo.sample_delivery_staff";
const SALES = "demo.sales";

export const PARAMETERS = {
  // Tested by Chemistry.
  lead: "sol_demo.demo_test_parameter_lead",
  // Tested by Microbiology.
  coliforms: "sol_demo.demo_test_parameter_coliforms",
};

// An image as the mobile app sends a signature or a photo: PNG bytes in base64.
export const PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

// A test request with its code and its samples, each as `{ model, id, code }`.
function readRequest(id) {
  return callAs(STAFF, "medilab.test.request", "read", [[id], ["code", "sample_ids"]]).then(([request]) =>
    callAs(STAFF, "medilab.sample", "read", [request.sample_ids, ["code"]]).then((samples) => ({
      model: "medilab.test.request",
      id,
      code: request.code,
      samples: samples.map((sample) => ({ model: "medilab.sample", id: sample.id, code: sample.code })),
    })),
  );
}

// The test request of a confirmed and paid order, confirmed by sample delivery staff, its samples expected.
export function orderRequest() {
  return orderAt("confirmed")
    .then((order) => callAs(SALES, "sale.order", "read", [[order.id], ["test_request_id"]]))
    .then(([order]) => {
      const id = order.test_request_id[0];
      callAs(STAFF, "medilab.test.request", "action_confirm", [[id]]);
      return readRequest(id);
    });
}

// A test request sample delivery staff create for Nước Uống Sạch: one sample of bottled water per entry of
// `samples`, each with the given parameters. Confirmed unless `confirm` is false.
export function staffRequest({ samples = [[PARAMETERS.lead]], confirm = true, expectedDate = false } = {}) {
  const refs = {};
  refAs(STAFF, "sol_demo.demo_customer_nuoc_sach").then(({ id }) => (refs.customer = id));
  refAs(STAFF, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (refs.sampleType = id));
  for (const xmlId of new Set(samples.flat())) {
    refAs(STAFF, xmlId).then(({ id }) => (refs[xmlId] = id));
  }
  return cy
    .then(() =>
      callAs(STAFF, "medilab.test.request", "create", [
        {
          customer_id: refs.customer,
          expected_date: expectedDate,
          sample_ids: samples.map((parameters, index) => [
            0,
            0,
            {
              customer_sample_name: `Nước đóng chai ${index + 1}`,
              sample_type_id: refs.sampleType,
              physical_state: "liquid",
              test_ids: parameters.map((xmlId) => [0, 0, { parameter_id: refs[xmlId] }]),
            },
          ]),
        },
      ]),
    )
    .then((id) => {
      if (confirm) {
        callAs(STAFF, "medilab.test.request", "action_confirm", [[id]]);
      }
      return readRequest(id);
    });
}

// Sample delivery staff record a sample's receipt.
export function receive(sample, condition = "good", note = false) {
  return callAs(STAFF, "medilab.sample", "action_receive", [[sample.id], "500 ml", condition, note, "Tủ lạnh 2"]);
}

// A handover record of a sample, signed by the customer on the phone of sample delivery staff.
export function signedRecord(request, sample, quantity = "500 ml", device = false) {
  return refAs(STAFF, "sol_demo.demo_person_sample_delivery_staff")
    .then(({ id }) =>
      callAs(STAFF, "medilab.handover.record", "create", [
        {
          request_id: request.id,
          handed_over_by_name: "Phạm Thị Hoa",
          received_by_id: id,
          sample_ids: [[0, 0, { sample_id: sample.id, quantity, condition: "good" }]],
        },
      ]),
    )
    .then((id) => callAs(STAFF, "medilab.handover.record", "action_sign", [[id], PNG, device]).then(() => ({ model: "medilab.handover.record", id })));
}

// A sample collection task of a test request, assigned to sample delivery staff by an administrator, as `{ model, id, name }`.
// A task created by hand names what to collect and opens no document.
export function collectionTask(request, values) {
  const name = `Collect ${request.code}`;
  return refAs("demo.administrator", "sol_laboratory.task_type_sample_collection")
    .then((type) =>
      refAs("demo.administrator", "sol_demo.demo_person_sample_delivery_staff").then((staff) =>
        callAs("demo.administrator", "medilab.task", "create", [{ type_id: type.id, name, assignee_id: staff.id, ...values }]),
      ),
    )
    .then((id) => ({ model: "medilab.task", id, name }));
}

// A time from now as Odoo stores it, in UTC.
export function inMinutes(minutes) {
  return new Date(Date.now() + minutes * 60000).toISOString().replace("T", " ").slice(0, 19);
}

// The testing tasks of a sample's tests, whoever may see them.
export function testingTasks(sample) {
  return callAs(STAFF, "medilab.sample", "read", [[sample.id], ["test_ids"]]).then(([read]) =>
    callAs("demo.administrator", "medilab.task", "search_read", [
      [
        ["document_model", "=", "medilab.sample.test"],
        ["document_id", "in", read.test_ids],
      ],
    ], { fields: ["department_id", "status", "assignee_id"] }),
  );
}

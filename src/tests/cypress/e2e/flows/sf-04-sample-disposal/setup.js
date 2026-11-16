import { callAs, refAs } from "../../../support/odoo";

const STAFF = "demo.sample_delivery_staff";
const ADMINISTRATOR = "demo.administrator";
export const TESTER = "demo.tester";

// Each demo sample type with the physical state of its samples.
export const SAMPLE_TYPES = {
  // Kept for 30 days, then poured into the drain.
  bottledWater: { xmlId: "sol_demo.demo_sample_type_bottled_water", physicalState: "liquid" },
  // Not kept; disposed of as organic waste.
  cabbage: { xmlId: "sol_demo.demo_sample_type_cabbage", physicalState: "solid" },
  // Not kept, with no disposal method.
  surfaceWater: { xmlId: "sol_demo.demo_sample_type_surface_water", physicalState: "liquid" },
};

// A day `days` from today as Odoo stores a date. The UTC day is never after the laboratory's day.
function day(days) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

// A test request of Nước Uống Sạch with one sample of the sample type, tested for lead by Chemistry when `lead` is
// set, yielded as `{ model, id, code }`.
function newSample(sampleType, { lead = false } = {}) {
  const refs = {};
  refAs(STAFF, "sol_demo.demo_customer_nuoc_sach").then(({ id }) => (refs.customer = id));
  refAs(STAFF, sampleType.xmlId).then(({ id }) => (refs.sampleType = id));
  refAs(STAFF, "sol_demo.demo_test_parameter_lead").then(({ id }) => (refs.lead = id));
  return cy
    .then(() =>
      callAs(STAFF, "medilab.test.request", "create", [
        {
          customer_id: refs.customer,
          sample_ids: [
            [
              0,
              0,
              {
                customer_sample_name: "Mẫu lưu sau báo cáo",
                sample_type_id: refs.sampleType,
                physical_state: sampleType.physicalState,
                test_ids: lead ? [[0, 0, { parameter_id: refs.lead }]] : [],
              },
            ],
          ],
        },
      ]),
    )
    .then((request) => callAs(STAFF, "medilab.test.request", "read", [[request], ["sample_ids"]]))
    .then(([request]) => callAs(STAFF, "medilab.sample", "read", [request.sample_ids, ["code"]]))
    .then(([sample]) => ({ model: "medilab.sample", id: sample.id, code: sample.code }));
}

// A sample whose report was issued: kept until `retainedFor` days from today when given, otherwise not kept.
// Issuing the report belongs to WF-06; the administrator sets the state it leaves the sample in.
export function reportedSample(sampleType, { retainedFor } = {}) {
  const kept = retainedFor !== undefined;
  return newSample(sampleType, { lead: kept }).then((sample) =>
    callAs(ADMINISTRATOR, "medilab.sample", "write", [
      [sample.id],
      kept ? { status: "retained", retained_until: day(retainedFor) } : { status: "reported" },
    ]).then(() => sample),
  );
}

// A sample of a test request sample delivery staff cancelled before it arrived.
export function cancelledSample() {
  return newSample(SAMPLE_TYPES.bottledWater).then((sample) =>
    callAs(STAFF, "medilab.sample", "read", [[sample.id], ["request_id"]])
      .then(([read]) => callAs(STAFF, "medilab.test.request", "action_cancel", [[read.request_id[0]]]))
      .then(() => sample),
  );
}

// A not-kept sample the tester has already disposed of by its sample type's method.
export function disposedSample() {
  return reportedSample(SAMPLE_TYPES.cabbage).then((sample) => callAs(TESTER, "medilab.sample", "action_dispose", [[sample.id]]).then(() => sample));
}

// The daily job that puts the samples whose retention ends soon or has ended on their department's to-do.
export function remindRetention() {
  return refAs(ADMINISTRATOR, "sol_laboratory.ir_cron_sample_retention_reminders").then(({ id }) =>
    callAs(ADMINISTRATOR, "ir.cron", "method_direct_trigger", [[id]]),
  );
}

// The retention tasks of a sample.
export function retentionTasks(sample) {
  return callAs(
    ADMINISTRATOR,
    "medilab.task",
    "search_read",
    [
      [
        ["type_id.code", "=", "sample_retention"],
        ["document_model", "=", "medilab.sample"],
        ["document_id", "=", sample.id],
      ],
    ],
    { fields: ["name", "status", "department_id", "assignee_id"] },
  );
}

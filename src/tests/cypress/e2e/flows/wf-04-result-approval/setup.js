import { callAs, refAs } from "../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
const TESTER = "demo.tester";
export const HEAD = "demo.head_of_department";
export const LAB_HEAD = "demo.lab_head";
const ADMINISTRATOR = "demo.administrator";

// Parameters that sol_demo seeds, both tested in Chemistry: lead on its machines, pH without one.
export const PARAMETERS = {
  lead: "sol_demo.demo_test_parameter_lead",
  ph: "sol_demo.demo_test_parameter_ph",
};

// The regulation bottled water is compared with; it limits lead to at most 0.010 mg/L.
const REGULATION = "sol_demo.demo_regulation_qcvn_6_1";

// Today's date plus some days, as Odoo stores a date.
function inDays(days) {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

// The testing task of a sample test.
function testingTask(testId) {
  return callAs(
    ADMINISTRATOR,
    "medilab.task",
    "search_read",
    [
      [
        ["document_model", "=", "medilab.sample.test"],
        ["document_id", "=", testId],
      ],
    ],
    { fields: ["name"], order: "id desc", limit: 1 },
  ).then(([task]) => ({ model: "medilab.task", id: task.id, name: task.name }));
}

// The tester books the recommended machine for the test and starts the booking, which starts the test.
export function bookAndStart(test) {
  callAs(TESTER, "medilab.sample.test", "action_schedule", [[test.id]]);
  return callAs(TESTER, "medilab.machine.booking", "search", [
    [
      ["sample_test_id", "=", test.id],
      ["status", "=", "scheduled"],
    ],
  ]).then(([id]) => {
    expect(id, "booking given a slot").to.be.a("number");
    test.booking = { model: "medilab.machine.booking", id };
    return callAs(TESTER, "medilab.machine.booking", "action_start", [[id]]);
  });
}

// Books and starts each test a machine runs; a test of a parameter no machine runs stays assigned.
function bookMachineTests(tests) {
  tests.forEach((test) =>
    callAs(ADMINISTRATOR, "medilab.parameter.method.machine", "search_count", [[["parameter_method_id.parameter_id", "=", test.parameterId]]]).then(
      (machines) => machines && bookAndStart(test),
    ),
  );
}

// A bottled water sample of a test request sample delivery staff created, received in good condition and handed over to
// Chemistry, whose tests, in the order of the parameters, are assigned to the tester. A test a machine runs is booked and
// in testing; one without a machine waits assigned. Its results are compared with `regulation`, an external ID or a
// `{ model, id }`; with false the sample has none.
export function sampleInTesting(parameters = [PARAMETERS.lead], { regulation = REGULATION } = {}) {
  const sample = { model: "medilab.sample" };
  const ids = {};
  refAs(RECEPTION, "sol_demo.demo_customer_green_farm").then(({ id }) => (ids.customer = id));
  refAs(RECEPTION, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (ids.sampleType = id));
  if (typeof regulation === "string") {
    refAs(RECEPTION, regulation).then(({ id }) => (ids.regulation = id));
  } else {
    ids.regulation = regulation && regulation.id;
  }
  const parameterIds = [];
  parameters.forEach((parameter) => refAs(RECEPTION, parameter).then(({ id }) => parameterIds.push(id)));
  cy.then(() =>
    callAs(RECEPTION, "medilab.test.request", "create", [
      {
        customer_id: ids.customer,
        expected_date: inDays(30),
        sample_ids: [
          [
            0,
            0,
            {
              customer_sample_name: `Nước đóng chai ${Date.now()}`,
              sample_type_id: ids.sampleType,
              physical_state: "liquid",
              regulation_id: ids.regulation || false,
              test_ids: parameterIds.map((id) => [0, 0, { parameter_id: id }]),
            },
          ],
        ],
      },
    ]),
  )
    .then((requestId) => {
      sample.requestId = requestId;
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[requestId]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", requestId]]], { fields: ["code", "test_ids"] });
    })
    .then(([read]) => {
      Object.assign(sample, { id: read.id, code: read.code });
      callAs(RECEPTION, "medilab.sample", "action_receive", [[read.id], "1 chai", "good"]);
      callAs(TESTER, "medilab.sample.handover", "receive_by_label", [read.code]);
      return callAs(ADMINISTRATOR, "medilab.sample.test", "read", [read.test_ids, ["parameter_id"]]);
    })
    .then((tests) => {
      sample.tests = tests.map((test) => ({ model: "medilab.sample.test", id: test.id, parameterId: test.parameter_id[0] }));
      sample.tests.forEach((test) => testingTask(test.id).then((task) => (test.task = task)));
    })
    .then(() => {
      const context = { active_ids: sample.tests.map((test) => test.task.id) };
      return refAs(HEAD, "sol_demo.demo_person_tester").then(({ id }) =>
        callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: id }], { context }).then((wizard) =>
          callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
        ),
      );
    })
    .then(() => bookMachineTests(sample.tests));
  return cy.then(() => sample);
}

// The test of the sample for a parameter given by its external ID.
export function testOf(sample, parameter) {
  return refAs(HEAD, parameter).then(({ id }) => sample.tests.find((test) => test.parameterId === id));
}

// A parameter of the Heavy metals group the administrator adds, tested in Chemistry by TCVN 7602:2007.
export function newParameter() {
  const parameter = { model: "medilab.test.parameter", name: `Arsenic (As) ${Date.now()}` };
  const ids = {};
  refAs(ADMINISTRATOR, "sol_demo.demo_parameter_group_heavy_metals").then(({ id }) => (ids.group = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_testing_method_tcvn_7602").then(({ id }) => (ids.method = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_measurement_unit_mg_kg").then(({ id }) => (ids.unit = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_hr_department_chemistry").then(({ id }) => (ids.department = id));
  return cy
    .then(() =>
      callAs(ADMINISTRATOR, "medilab.test.parameter", "create", [
        {
          name: parameter.name,
          main_group_id: ids.group,
          group_ids: [[6, 0, [ids.group]]],
          method_ids: [[0, 0, { method_id: ids.method, unit_id: ids.unit, department_id: ids.department, is_default: true }]],
        },
      ]),
    )
    .then((id) => Object.assign(parameter, { id }));
}

// A regulation for bottled water the administrator adds, limiting lead to at most `max` mg/L.
export function newRegulation(max) {
  const ids = {};
  refAs(ADMINISTRATOR, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (ids.sampleType = id));
  refAs(ADMINISTRATOR, PARAMETERS.lead).then(({ id }) => (ids.lead = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_measurement_unit_mg_l").then(({ id }) => (ids.unit = id));
  return cy
    .then(() =>
      callAs(ADMINISTRATOR, "medilab.regulation", "create", [
        {
          code: `QCVN ${Date.now()}/BYT`,
          name: "Quy chuẩn nước đóng chai của khách hàng",
          sample_type_ids: [[6, 0, [ids.sampleType]]],
          limit_ids: [[0, 0, { parameter_id: ids.lead, unit_id: ids.unit, max_set: true, max_value: max, decimals: 3 }]],
        },
      ]),
    )
    .then((id) => ({ model: "medilab.regulation", id }));
}

// A result entered for the test as a login, as the result form saves it.
export function enterResult(test, values, login = TESTER) {
  return callAs(login, "medilab.test.result", "create", [{ sample_test_id: test.id, ...values }]).then((id) => ({
    model: "medilab.test.result",
    id,
  }));
}

// A result entered and sent for approval: the tester signs the first level of its chain.
export function sentResult(test, values, { enteredBy = TESTER } = {}) {
  return enterResult(test, values, enteredBy).then((result) => {
    callAs(TESTER, "medilab.test.result", "action_sign", [[result.id]]);
    return cy.wrap(result, { log: false });
  });
}

// A result the head of department approved.
export function approvedResult(test, values) {
  return sentResult(test, values).then((result) => {
    callAs(HEAD, "medilab.test.result", "action_sign", [[result.id]]);
    return cy.wrap(result, { log: false });
  });
}

// A result the head of department rejected with a reason, which sends its test back to testing.
export function rejectedResult(test, values, reason) {
  return sentResult(test, values).then((result) => {
    callAs(HEAD, "medilab.test.result", "action_reject", [[result.id], reason]);
    return cy.wrap(result, { log: false });
  });
}

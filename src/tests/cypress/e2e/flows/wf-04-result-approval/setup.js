import { callAs, refAs } from "../../../support/odoo";
import { PARAMETERS, assign, book, receivedSample, testingTasks as sampleTestingTasks, testOf } from "../wf-03-testing-scheduling/setup";
import { ADMINISTRATOR, TESTER, assignedTest } from "../wf-05-outsourced-testing/setup";

export { TESTER, assignedTest };
export const HEAD = "demo.head_of_department";
export const LAB_HEAD = "demo.lab_head";

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

// A result entered for the test as the tester, as the result form saves it.
export function enteredResult(test, values) {
  return callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: test.id, ...values }]).then((id) => ({
    model: "medilab.test.result",
    id,
  }));
}

// A result the tester entered and sent, and the head of department approved.
export function approvedResult(test, values) {
  return enteredResult(test, values).then((result) => {
    callAs(TESTER, "medilab.test.result", "action_sign", [[result.id]]);
    callAs(HEAD, "medilab.test.result", "action_sign", [[result.id]]);
    return cy.wrap(result, { log: false });
  });
}

// A lead test assigned to the tester and booked on its machine, which chooses its way of testing.
export function bookedLead() {
  return receivedSample([PARAMETERS.lead]).then((sample) => {
    assign(sample);
    return testOf(sample, PARAMETERS.lead).then((lead) => book(lead).then(() => lead));
  });
}

// A bottled water sample whose lead and pH tests are assigned to the tester. The lead test is booked on its machine
// and started, so it is in testing with its booking; pH, which no machine runs, waits assigned.
export function leadInTesting() {
  return receivedSample([PARAMETERS.lead, PARAMETERS.ph]).then((sample) => {
    assign(sample);
    testOf(sample, PARAMETERS.ph).then((ph) => (sample.ph = ph));
    testOf(sample, PARAMETERS.lead)
      .then((lead) => {
        sample.lead = lead;
        return book(lead);
      })
      .then((booking) => {
        expect(booking, "booking given a slot").to.include({ status: "scheduled" });
        sample.lead.booking = { model: booking.model, id: booking.id };
        callAs(TESTER, "medilab.machine.booking", "action_start", [[booking.id]]);
      });
    return cy.then(() => sample);
  });
}

// A parameter of the Heavy metals group the administrator adds, tested in Chemistry by TCVN 7602:2007.
export function newParameter() {
  const parameter = { model: "medilab.test.parameter", name: `Arsenic (As) ${Date.now()}` };
  const ids = {};
  refAs(ADMINISTRATOR, "sol_demo.demo_parameter_group_heavy_metals").then(({ id }) => (ids.group = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_testing_method_tcvn_7602").then(({ id }) => (ids.method = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_hr_department_chemistry").then(({ id }) => (ids.department = id));
  return cy
    .then(() =>
      callAs(ADMINISTRATOR, "medilab.test.parameter", "create", [
        {
          name: parameter.name,
          main_group_id: ids.group,
          group_ids: [[6, 0, [ids.group]]],
          method_ids: [[0, 0, { method_id: ids.method, department_id: ids.department }]],
        },
      ]),
    )
    .then((id) => Object.assign(parameter, { id }));
}

// A regulation for bottled water the administrator adds, limiting lead in it to at most `max` mg/L.
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
          limit_ids: [
            [0, 0, { parameter_id: ids.lead, sample_type_id: ids.sampleType, unit_id: ids.unit, max_set: true, max_value: max, decimals: 3 }],
          ],
        },
      ]),
    )
    .then((id) => ({ model: "medilab.regulation", id }));
}

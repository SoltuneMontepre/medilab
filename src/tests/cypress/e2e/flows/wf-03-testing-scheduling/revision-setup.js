import { callAs, refAs } from "../../../support/odoo";
import { ADMINISTRATOR, HEAD, awayFromQuarterHour, ownTests, receiveInDepartments, testingTasks } from "./setup";

const RECEPTION = "demo.sample_delivery_staff";
export const RUN = 4 * 3600000;

// A UTC time as Odoo stores it.
export function odooTime(milliseconds) {
  return new Date(milliseconds).toISOString().slice(0, 19).replace("T", " ");
}

// Milliseconds of an Odoo UTC time.
export function milliseconds(value) {
  return Date.parse(`${value.replace(" ", "T")}Z`);
}

function inDays(days) {
  return odooTime(Date.now() + days * 86400000).slice(0, 10);
}

// The sample tests the scenarios made, which cancelTests cancels.
const fixture = { testIds: [] };

// The head cancels the tests the scenario made, which ends their testing tasks and takes their proposals out of the plan.
export function cancelTests() {
  const ids = fixture.testIds.splice(0);
  return cy.then(() =>
    ids.forEach((id) => callAs(HEAD, "medilab.sample.test", "action_cancel", [[id], "The test fixture is over."])),
  );
}

// A gas chromatograph that runs one method in 4 hours, with a tester of Chemistry who alone is authorized for its
// parameter. The names carry the time, so a rerun on the same database starts from records of its own.
function gasChromatograph(stamp) {
  const made = {};
  refAs(ADMINISTRATOR, "sol_demo.demo_hr_department_chemistry").then(({ id }) => (made.departmentId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_testing_field_chemistry").then(({ id }) => (made.fieldId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_parameter_group_organophosphates").then(({ id }) => (made.groupId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_sample_type_cabbage").then(({ id }) => (made.typeId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_measurement_unit_mg_kg").then(({ id }) => (made.unitId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_customer_green_farm").then(({ id }) => (made.customerId = id));
  refAs(ADMINISTRATOR, "sol_demo.demo_location_chemistry_bench_3").then(({ id }) => (made.locationId = id));
  cy.then(() =>
    callAs(ADMINISTRATOR, "medilab.machine", "create", [
      {
        code: `GC-${stamp}`,
        name: `Gas chromatograph ${stamp}`,
        location_id: made.locationId,
        service_ids: [[0, 0, { kind: "calibration", service_date: inDays(-30), next_due_date: inDays(300) }]],
      },
    ]),
  )
    .then((id) => {
      made.machineId = id;
      return callAs(ADMINISTRATOR, "medilab.testing.method", "create", [
        { code: `LAB-GC-${stamp}`, name: `Diazinon residues by gas chromatography ${stamp}`, field_id: made.fieldId },
      ]);
    })
    .then((id) => {
      made.methodId = id;
      return callAs(ADMINISTRATOR, "medilab.test.parameter", "create", [
        { name: `Diazinon ${stamp}`, group_ids: [[6, 0, [made.groupId]]], main_group_id: made.groupId },
      ]);
    })
    .then((id) => {
      made.parameterId = id;
      made.parameterName = `Diazinon ${stamp}`;
      return callAs(ADMINISTRATOR, "medilab.parameter.method", "create", [
        { parameter_id: id, method_id: made.methodId, department_id: made.departmentId },
      ]);
    })
    .then((id) => {
      made.wayId = id;
      callAs(ADMINISTRATOR, "medilab.parameter.method.sample.type", "create", [
        { parameter_id: made.parameterId, parameter_method_id: id, sample_type_id: made.typeId, unit_id: made.unitId, is_default: true },
      ]);
      callAs(ADMINISTRATOR, "medilab.machine.method", "create", [{ machine_id: made.machineId, method_id: made.methodId, duration_minutes: 240 }]);
      return callAs(ADMINISTRATOR, "medilab.person", "create", [{ name: `Tester GC ${stamp}`, department_id: made.departmentId }]);
    })
    .then((id) => {
      made.testerId = id;
      return callAs(ADMINISTRATOR, "medilab.parameter.authorization", "create", [{ person_id: id, parameter_id: made.parameterId }]);
    });
  return cy.then(() => made);
}

// A cabbage sample tested for the parameter, received by Chemistry, with its testing task assigned to the tester.
function receivedTest(made, name) {
  let test;
  return callAs(RECEPTION, "medilab.test.request", "create", [
    {
      customer_id: made.customerId,
      expected_date: inDays(10),
      sample_ids: [
        [0, 0, { customer_sample_name: name, sample_type_id: made.typeId, physical_state: "solid", test_ids: [[0, 0, { parameter_id: made.parameterId }]] }],
      ],
    },
  ])
    .then((requestId) => {
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[requestId]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", requestId]]], { fields: ["code", "test_ids"] });
    })
    .then(([read]) => {
      callAs(RECEPTION, "medilab.sample", "action_receive", [[read.id], "1 kg", "good"]);
      receiveInDepartments({ id: read.id, code: read.code });
      test = { model: "medilab.sample.test", id: read.test_ids[0] };
      return testingTasks({ tests: [test] });
    })
    .then(([task]) => {
      ownTests([test.id]);
      fixture.testIds.push(test.id);
      const context = { active_ids: [task.id] };
      return callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: made.testerId }], { context }).then((wizard) =>
        callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
      );
    })
    .then(() => test);
}

// The head of department sets the internal due date of the test, as the Change Due Date dialog does.
export function dueAt(test, dueDate) {
  return callAs(HEAD, "medilab.sample.test.due.date.change", "create", [
    { sample_test_id: test.id, due_date: odooTime(dueDate), reason: "The customer confirmed the date it needs the results." },
  ]).then((wizard) => callAs(HEAD, "medilab.sample.test.due.date.change", "action_change", [[wizard]]));
}

// The booking the head approved for the test.
export function scheduledBooking(test) {
  return callAs(HEAD, "medilab.machine.booking", "search_read", [[["sample_test_id", "=", test.id], ["status", "=", "scheduled"]]], {
    fields: ["starts_at", "ends_at", "status"],
  }).then(([booking]) => booking);
}

// The current booking of the test: scheduled or still a proposal.
export function currentBooking(test) {
  return callAs(HEAD, "medilab.machine.booking", "search_read", [[["sample_test_id", "=", test.id], ["status", "in", ["proposed", "scheduled"]]]], {
    fields: ["starts_at", "ends_at", "status"],
  }).then(([booking]) => booking);
}

// The head records OverTime for the tester in the 4 hours that follow the given time.
export function recordOvertime(made, start) {
  return callAs(HEAD, "medilab.overtime", "create", [
    { person_id: made.testerId, starts_at: odooTime(start), ends_at: odooTime(start + RUN), reason: "Urgent work must not delay the samples received before it." },
  ]);
}

// The GC-01 example of the scheduling spec: Z and Y are normal tests booked one after the other on the one gas
// chromatograph, both due when Y's interval ends, and urgent X, due then too, needs Z's interval. With room for the
// moves, the three are due 4 hours later, when the OverTime the test records after Y's interval ends. Yields the made
// resources, the three tests, their bookings and the due date.
export function urgentNeedsScheduledSlots({ roomForTheMoves = false } = {}) {
  const stamp = Date.now();
  const scenario = {};
  awayFromQuarterHour();
  gasChromatograph(stamp).then((made) => {
    scenario.made = made;
    receivedTest(made, `Cải bắp Z ${stamp}`).then((test) => (scenario.z = test));
    receivedTest(made, `Cải bắp Y ${stamp}`).then((test) => (scenario.y = test));
  });
  cy.then(() => {
    callAs(HEAD, "medilab.sample.test", "action_approve_booking", [[scenario.z.id]]);
    callAs(HEAD, "medilab.sample.test", "action_approve_booking", [[scenario.y.id]]);
    return scheduledBooking(scenario.z).then((booking) => (scenario.zBooking = booking));
  });
  cy.then(() => scheduledBooking(scenario.y).then((booking) => (scenario.yBooking = booking)));
  cy.then(() => {
    scenario.due = milliseconds(scenario.yBooking.ends_at) + (roomForTheMoves ? RUN : 0);
    return receivedTest(scenario.made, `Cải bắp X ${stamp}`).then((test) => (scenario.x = test));
  });
  cy.then(() => {
    [scenario.z, scenario.y, scenario.x].forEach((test) => dueAt(test, scenario.due));
    return callAs(HEAD, "medilab.sample.test.urgent.mark", "create", [
      { sample_test_id: scenario.x.id, reason: "The customer needs it to clear a shipment." },
    ]).then((wizard) => callAs(HEAD, "medilab.sample.test.urgent.mark", "action_mark", [[wizard]]));
  });
  return cy.then(() => scenario);
}

// The proposed plan revision of Chemistry.
export function openRevision() {
  return callAs(HEAD, "medilab.plan.revision", "search_read", [[["status", "=", "proposed"]]], {
    fields: ["status", "reason", "move_ids"],
  }).then(([revision]) => revision);
}

// The moves of a revision, with the booking and state of each.
export function movesOf(revision) {
  return callAs(HEAD, "medilab.plan.revision.move", "read", [revision.move_ids, ["booking_id", "status", "starts_at", "sample_test_id"]]);
}

import { callAs, refAs } from "../../../support/odoo";

export const ADMIN = "demo.administrator";
export const HEAD = "demo.head_of_department";
export const TESTER = "demo.tester";
const RECEPTION = "demo.sample_delivery_staff";
const DAY = 86400000;
const OPEN_TESTS = ["waiting", "assigned", "testing"];

// A UTC time as Odoo stores it.
export const odooTime = (milliseconds) => new Date(milliseconds).toISOString().slice(0, 19).replace("T", " ");

// Today's date plus some days, as Odoo stores a date.
export const inDays = (days) => odooTime(Date.now() + days * DAY).slice(0, 10);

// A stored date as the English interface types it.
export const typed = (date) => `${date.slice(5, 7)}/${date.slice(8, 10)}/${date.slice(0, 4)}`;

function create(login, model, values) {
  return callAs(login, model, "create", [values]);
}

// A calibration record that ends `days` from today; the machine is calibrated today.
export const calibration = (days = 365) => ({ kind: "calibration", service_date: inDays(0), next_due_date: inDays(days) });

// Machines linked to one method of their own, all able to run the same way of testing, and tests of that way waiting
// at the tester. The first `book` tests are booked as the head of department approves the department's plan; the
// others wait for the plan. A machine is calibrated unless `calibrated` is false. Machines take the codes <tag>-A,
// <tag>-B, ..., so the plan prefers the first one. The test registers the fixture first, so a failed setup is still
// released.
export function machineFixture({ tests = 1, book = tests, machines = 1, capacity = 1, calibrated = true } = {}, register = () => {}) {
  const fixture = { tag: `Cu-SF05-${Date.now()}`, tests: [], tasks: [], bookings: [], machines: [] };
  register(fixture);
  const refs = {
    department: "sol_demo.demo_hr_department_chemistry",
    sampleType: "sol_demo.demo_sample_type_bottled_water",
    customer: "sol_demo.demo_customer_green_farm",
    group: "sol_demo.demo_parameter_group_heavy_metals",
    field: "sol_demo.demo_testing_field_chemistry",
    unit: "sol_demo.demo_measurement_unit_mg_l",
    tester: "sol_demo.demo_person_tester",
  };
  Object.entries(refs).forEach(([key, xmlId]) => refAs(ADMIN, xmlId).then(({ id }) => (fixture[key] = id)));
  cy.then(() =>
    create(ADMIN, "medilab.location", {
      code: fixture.tag,
      name: `Copper preparation ${fixture.tag}`,
      department_id: fixture.department,
      is_bookable: true,
    }),
  ).then((id) => (fixture.room = id));
  cy.then(() =>
    create(ADMIN, "medilab.testing.method", {
      code: fixture.tag,
      name: `Copper measurement ${fixture.tag}`,
      field_id: fixture.field,
      step_ids: [[0, 0, { sequence: 1, duration_minutes: 15, instruction: "Prepare the copper standard.", location_id: fixture.room }]],
    }),
  ).then((id) => (fixture.method = id));
  cy.then(() =>
    create(ADMIN, "medilab.test.parameter", {
      name: `Copper (Cu) ${fixture.tag}`,
      main_group_id: fixture.group,
      group_ids: [[6, 0, [fixture.group]]],
    }),
  ).then((id) => (fixture.parameter = id));
  cy.then(() => create(ADMIN, "medilab.parameter.authorization", { person_id: fixture.tester, parameter_id: fixture.parameter }));
  cy.then(() =>
    create(ADMIN, "medilab.parameter.method", {
      parameter_id: fixture.parameter,
      method_id: fixture.method,
      department_id: fixture.department,
      applicability_ids: [[0, 0, { sample_type_id: fixture.sampleType, unit_id: fixture.unit, is_default: true }]],
    }),
  ).then((id) => (fixture.way = id));
  for (let index = 0; index < machines; index += 1) {
    const letter = String.fromCharCode(65 + index);
    cy.then(() =>
      create(ADMIN, "medilab.machine", {
        code: `${fixture.tag}-${letter}`,
        name: `Copper spectrometer ${fixture.tag}-${letter}`,
        location_id: fixture.room,
        method_ids: [[0, 0, { method_id: fixture.method, duration_minutes: 30, capacity }]],
        service_ids: calibrated ? [[0, 0, calibration()]] : [],
      }),
    ).then((id) => fixture.machines.push(id));
  }
  cy.then(() => (fixture.machine = fixture.machines[0]));
  for (let index = 0; index < tests; index += 1) {
    cy.then(() =>
      create(RECEPTION, "medilab.test.request", {
        customer_id: fixture.customer,
        committed_date: inDays(30),
        sample_ids: [
          [
            0,
            0,
            {
              customer_sample_name: `Nước uống ${fixture.tag}-${index}`,
              sample_type_id: fixture.sampleType,
              physical_state: "liquid",
              test_ids: [[0, 0, { parameter_id: fixture.parameter }]],
            },
          ],
        ],
      }),
    )
      .then((request) => {
        callAs(RECEPTION, "medilab.test.request", "action_confirm", [[request]]);
        return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", request]]], { fields: ["code", "test_ids"] });
      })
      .then(([sample]) => {
        fixture.tests.push(sample.test_ids[0]);
        callAs(RECEPTION, "medilab.sample", "action_receive", [[sample.id], "1 chai", "good"]);
        callAs(TESTER, "medilab.sample.handover", "receive_by_label", [sample.code]);
        return callAs(
          ADMIN,
          "medilab.task",
          "search_read",
          [
            [
              ["document_model", "=", "medilab.sample.test"],
              ["document_id", "=", sample.test_ids[0]],
            ],
          ],
          { fields: ["name"] },
        );
      })
      .then(([task]) => {
        fixture.tasks.push(task.id);
        const context = { active_ids: [task.id] };
        return create(HEAD, "medilab.task.reassign", {
          task_ids: [[6, 0, [task.id]]],
          assignee_id: fixture.tester,
          department_id: fixture.department,
        }).then((wizard) => callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }));
      });
    if (index < book) cy.then(() => approve(fixture, fixture.tests[index]));
  }
  return cy.then(() => fixture);
}

// The head of department approves the slot the department's plan proposes for the test, and yields the booking.
export function approve(fixture, test) {
  callAs(HEAD, "medilab.sample.test", "action_approve_booking", [[test]]);
  return callAs(ADMIN, "medilab.machine.booking", "search", [
    [
      ["sample_test_id", "=", test],
      ["status", "=", "scheduled"],
    ],
  ]).then(([booking]) => {
    expect(booking, "the approved booking").to.be.a("number");
    fixture.bookings.push(booking);
    return booking;
  });
}

// machine_warning is left out: a booking on a machine under repair that has a calibration date cannot be read with it.
export const BOOKING_FIELDS = ["status", "machine_id", "method_id", "starts_at", "ends_at", "person_id"];

// The fixture's bookings that are not cancelled, by id.
export function bookingsOf(fixture, fields = BOOKING_FIELDS) {
  return callAs(
    ADMIN,
    "medilab.machine.booking",
    "search_read",
    [
      [
        ["sample_test_id", "in", fixture.tests],
        ["status", "!=", "cancelled"],
      ],
    ],
    { fields, order: "id" },
  );
}

export function testsOf(fixture, fields) {
  return callAs(ADMIN, "medilab.sample.test", "read", [fixture.tests, fields]);
}

// The people the notices of an event about these records reached, as their logins.
export function notified(model, ids, subtype) {
  return callAs(
    ADMIN,
    "mail.notification",
    "search_read",
    [
      [
        ["mail_message_id.model", "=", model],
        ["mail_message_id.res_id", "in", ids],
        ["mail_message_id.subtype_id.code", "=", subtype],
      ],
    ],
    { fields: ["res_partner_id"] },
  ).then((notices) =>
    callAs(ADMIN, "res.users", "search_read", [[["partner_id", "in", notices.map((notice) => notice.res_partner_id[0])]]], {
      fields: ["login"],
    }).then((users) => users.map((user) => user.login).sort()),
  );
}

// Every machine of the fixture back in use with a valid calibration, so no booking is left on a machine that is not fit
// to use, and its open tests cancelled by the head of department, which ends their bookings and leaves nothing in the
// plan for the tests of other specs to be planned around.
export function release(fixture) {
  if (!fixture?.machines?.length) return null;
  callAs(ADMIN, "medilab.machine", "read", [fixture.machines, ["status"]]).then((machines) =>
    machines
      .filter((machine) => machine.status !== "in_use")
      .forEach((machine) => {
        callAs(ADMIN, "medilab.machine.service", "create", [{ machine_id: machine.id, ...calibration() }]);
        callAs(ADMIN, "medilab.machine", "write", [[machine.id], { status: "in_use" }]);
      }),
  );
  callAs(ADMIN, "medilab.sample.test", "search", [
    [
      ["id", "in", fixture.tests],
      ["status", "in", OPEN_TESTS],
    ],
  ]).then((tests) => tests.length && callAs(HEAD, "medilab.sample.test", "action_cancel", [tests, "Cypress SF-05 clean-up."]));
  return cy.then(() => null);
}

import { callAs, refAs } from "../../../../support/odoo";

export const ADMIN = "demo.administrator";
export const HEAD = "demo.head_of_department";
export const TESTER = "demo.tester";
const RECEPTION = "demo.sample_delivery_staff";
const OPEN = ["queued", "scheduled", "in_progress"];

export const odooTime = (milliseconds) => new Date(milliseconds).toISOString().slice(0, 19).replace("T", " ");
export const milliseconds = (value) => new Date(`${value}Z`).getTime();

// The next Monday morning in the demo users' Vietnamese working calendar, away from today's slot boundary.
function nextMonday() {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + ((8 - day.getUTCDay()) % 7 || 7));
  day.setUTCHours(2, 0, 0, 0);
  return day.getTime();
}

function create(login, model, values) {
  return callAs(login, model, "create", [values]);
}

// Each test owns its catalog and resources; no seeded booking or shared machine is moved to force availability.
export function schedulingFixture(count = 2, register = () => {}) {
  const fixture = { tag: `Cu-UI-${Date.now()}`, tasks: [], tests: [], bookings: [], eventIds: [] };
  register(fixture);
  const refs = {
    department: "sol_demo.demo_hr_department_chemistry",
    sampleType: "sol_demo.demo_sample_type_bottled_water",
    customer: "sol_demo.demo_customer_green_farm",
    group: "sol_demo.demo_parameter_group_heavy_metals",
    field: "sol_demo.demo_testing_field_chemistry",
    unit: "sol_demo.demo_measurement_unit_mg_l",
    tester: "sol_demo.demo_person_tester",
    head: "sol_demo.demo_person_head_of_department",
  };
  Object.entries(refs).forEach(([key, xmlId]) => refAs(ADMIN, xmlId).then(({ id }) => (fixture[key] = id)));
  cy.then(() => create(ADMIN, "medilab.location", {
    code: fixture.tag,
    name: `Copper preparation ${fixture.tag}`,
    department_id: fixture.department,
    is_bookable: true,
  })).then((id) => (fixture.room = id));
  cy.then(() => create(ADMIN, "medilab.testing.method", {
    code: fixture.tag,
    name: `Copper measurement ${fixture.tag}`,
    field_id: fixture.field,
    step_ids: [[0, 0, { sequence: 1, duration_minutes: 15, instruction: "Prepare the copper standard.", location_id: fixture.room }]],
  })).then((id) => (fixture.method = id));
  cy.then(() => create(ADMIN, "medilab.test.parameter", {
    name: `Copper (Cu) ${fixture.tag}`,
    main_group_id: fixture.group,
    group_ids: [[6, 0, [fixture.group]]],
    sample_type_ids: [[6, 0, [fixture.sampleType]]],
  })).then((id) => (fixture.parameter = id));
  cy.then(() => create(ADMIN, "medilab.parameter.method", {
    parameter_id: fixture.parameter,
    method_id: fixture.method,
    unit_id: fixture.unit,
    department_id: fixture.department,
    is_default: true,
  })).then((id) => (fixture.way = id));
  cy.then(() => create(ADMIN, "medilab.machine", {
    code: fixture.tag,
    name: `Copper spectrometer ${fixture.tag}`,
    location_id: fixture.room,
    parameter_method_ids: [[0, 0, { parameter_method_id: fixture.way, run_minutes: 30 }]],
    service_ids: [[0, 0, {
      kind: "calibration",
      service_date: odooTime(Date.now()).slice(0, 10),
      next_due_date: odooTime(Date.now() + 365 * 86400000).slice(0, 10),
    }]],
  })).then((id) => (fixture.machine = id));
  for (let index = 0; index < count; index += 1) {
    cy.then(() => create(RECEPTION, "medilab.test.request", {
      customer_id: fixture.customer,
      expected_date: odooTime(Date.now() + 30 * 86400000).slice(0, 10),
      sample_ids: [[0, 0, {
        customer_sample_name: `Nước uống ${fixture.tag}-${index}`,
        sample_type_id: fixture.sampleType,
        physical_state: "liquid",
        test_ids: [[0, 0, { parameter_id: fixture.parameter }]],
      }]],
    })).then((request) => {
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[request]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", request]]], { fields: ["test_ids"] });
    }).then(([sample]) => {
      fixture.tests.push(sample.test_ids[0]);
      callAs(RECEPTION, "medilab.sample", "action_receive", [[sample.id], "1 chai", "good"]);
      return callAs(ADMIN, "medilab.task", "search_read", [
        [["document_model", "=", "medilab.sample.test"], ["document_id", "=", sample.test_ids[0]]],
      ], { fields: ["name"] });
    }).then(([task]) => {
      fixture.tasks.push(task.id);
      const context = { active_ids: [task.id] };
      return create(HEAD, "medilab.task.reassign", { task_ids: [[6, 0, [task.id]]], assignee_id: fixture.tester, department_id: fixture.department })
        .then((wizard) => callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }));
    }).then(() => callAs(TESTER, "medilab.sample.test", "action_schedule", [[fixture.tests[index]]]))
      .then(() => callAs(ADMIN, "medilab.machine.booking", "search_read", [
        [["sample_test_id", "=", fixture.tests[index]], ["status", "in", OPEN]],
      ], { fields: ["calendar_event_id", "room_event_ids"] }))
      .then((bookings) => {
        expect(bookings, "one active booking per test").to.have.length(1);
        const [booking] = bookings;
        fixture.bookings.push(booking.id);
        fixture.eventIds.push(booking.calendar_event_id[0], ...booking.room_event_ids);
        return callAs(TESTER, "medilab.machine.booking", "write", [[booking.id], { starts_at: odooTime(nextMonday() + index * 3600000) }]);
      });
  }
  return cy.then(() => fixture);
}

export function snapshot(fixture) {
  const graph = {};
  const reads = {
    tasks: ["medilab.task", fixture.tasks, ["status", "assignee_id", "assigned_by_id", "department_id", "reassign_reason", "note", "planned_start", "planned_end", "write_date"]],
    tests: ["medilab.sample.test", fixture.tests, ["status", "parameter_method_id", "due_date", "write_date"]],
    bookings: ["medilab.machine.booking", fixture.bookings, ["sample_test_id", "task_id", "machine_id", "person_id", "starts_at", "ends_at", "status", "calendar_event_id", "room_event_ids", "write_date"]],
  };
  Object.entries(reads).forEach(([key, [model, ids, fields]]) => {
    callAs(ADMIN, model, "read", [ids, fields]).then((rows) => (graph[key] = rows.sort((left, right) => left.id - right.id)));
  });
  callAs(ADMIN, "calendar.event", "search_read", [
    ["|", "|", ["id", "in", fixture.eventIds], ["machine_booking_id", "in", fixture.bookings], ["name", "ilike", fixture.tag]],
  ], {
    fields: ["name", "start", "stop", "active", "user_id", "partner_ids", "location_id", "machine_booking_id", "step_id", "write_date"],
    order: "id",
    context: { active_test: false },
  }).then((events) => (graph.events = events));
  callAs(ADMIN, "medilab.machine.booking", "search_read", [
    [["sample_test_id", "in", fixture.tests], ["status", "in", OPEN]],
  ], { fields: ["sample_test_id"], order: "id" }).then((bookings) => (graph.activeBookings = bookings));
  return cy.then(() => graph);
}

export function release(fixture) {
  if (!fixture?.machine) return null;
  return callAs(ADMIN, "medilab.machine.booking", "search", [
    [["machine_id", "=", fixture.machine], ["status", "in", ["queued", "scheduled"]]],
  ]).then((ids) => ids.length ? callAs(ADMIN, "medilab.machine.booking", "action_cancel", [ids]) : null);
}

export function typeStart(value) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true,
  }).formatToParts(new Date(`${value}Z`));
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  const text = `${values.month}/${values.day}/${values.year} ${values.hour}:${values.minute}:${values.second} ${values.dayPeriod}`;
  cy.get('.o_field_widget[name="starts_at"] .o_input').first().focus();
  cy.get('.o_field_widget[name="starts_at"] input').clear().type(text).blur();
}

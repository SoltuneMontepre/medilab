import { callAs, refAs } from "../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
export const HEAD = "demo.head_of_department";
export const TESTER = "demo.tester";
export const ADMINISTRATOR = "demo.administrator";

// Parameters that sol_demo seeds: lead runs on the Chemistry machines, pH in Chemistry without one, coliforms in Microbiology.
export const PARAMETERS = {
  lead: "sol_demo.demo_test_parameter_lead",
  ph: "sol_demo.demo_test_parameter_ph",
  coliforms: "sol_demo.demo_test_parameter_coliforms",
};

export const PEOPLE = {
  tester: "sol_demo.demo_person_tester",
  chemistryTester: "sol_demo.demo_person_chemistry_tester",
};

export const URGENCY = "sol_laboratory.urgency_hours";
const SETTING_KEYS = [URGENCY, "sol_laboratory.safety_margin_days"];
const QUARTER_HOUR = 15 * 60000;
const MINUTE = 60000;
const BOOKING_FIELDS = [
  "display_name",
  "machine_id",
  "person_id",
  "starts_at",
  "ends_at",
  "status",
  "calendar_event_id",
  "room_event_ids",
  "task_id",
];

// A UTC time as Odoo stores it.
function odooTime(milliseconds) {
  return new Date(milliseconds).toISOString().slice(0, 19).replace("T", " ");
}

// Today's date plus some days, as Odoo stores a date.
function inDays(days) {
  return odooTime(Date.now() + days * 86400000).slice(0, 10);
}

// The scheduler starts free slots on the quarter hour after now, so a recommendation read in the last seconds before
// one moves on before it is booked. Waits those seconds out.
export function awayFromQuarterHour() {
  return cy.then(() => {
    const left = QUARTER_HOUR - (Date.now() % QUARTER_HOUR);
    if (left < 45000) {
      cy.wait(left + 1000);
    }
  });
}

// The testing tasks of the sample's tests, in whichever department they wait.
export function testingTasks(sample) {
  return callAs(
    ADMINISTRATOR,
    "medilab.task",
    "search_read",
    [
      [
        ["document_model", "=", "medilab.sample.test"],
        ["document_id", "in", sample.tests.map((test) => test.id)],
      ],
    ],
    { fields: ["name", "status", "assignee_id", "department_id", "document_id"] },
  );
}

// A sample received in good condition, whose tests, in the order of the parameters, wait as testing tasks in the queues
// of their departments. Its results are promised `days` from today, so its tests are due that many days less the safety
// margin.
export function receivedSample(parameters = [PARAMETERS.lead], { days = 30 } = {}) {
  const sample = { model: "medilab.sample" };
  const parameterIds = [];
  refAs(RECEPTION, "sol_demo.demo_customer_green_farm").then(({ id }) => (sample.customerId = id));
  refAs(RECEPTION, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (sample.typeId = id));
  parameters.forEach((parameter) => refAs(RECEPTION, parameter).then(({ id }) => parameterIds.push(id)));
  cy.then(() =>
    callAs(RECEPTION, "medilab.test.request", "create", [
      {
        customer_id: sample.customerId,
        expected_date: inDays(days),
        sample_ids: [
          [
            0,
            0,
            {
              customer_sample_name: `Nước đóng chai ${Date.now()}`,
              sample_type_id: sample.typeId,
              physical_state: "liquid",
              test_ids: parameterIds.map((id) => [0, 0, { parameter_id: id }]),
            },
          ],
        ],
      },
    ]),
  )
    .then((requestId) => {
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[requestId]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", requestId]]], { fields: ["code", "test_ids"] });
    })
    .then(([read]) => {
      Object.assign(sample, { id: read.id, code: read.code });
      callAs(RECEPTION, "medilab.sample", "action_receive", [[read.id], "1 chai", "good"]);
      return callAs(ADMINISTRATOR, "medilab.sample.test", "read", [read.test_ids, ["parameter_id"]]);
    })
    .then((tests) => {
      sample.tests = tests.map((test) => ({ model: "medilab.sample.test", id: test.id, parameterId: test.parameter_id[0] }));
      return testingTasks(sample);
    })
    .then((tasks) =>
      sample.tests.forEach((test) => {
        const task = tasks.find((read) => read.document_id === test.id);
        test.task = { model: "medilab.task", id: task.id, name: task.name };
      }),
    );
  return cy.then(() => sample);
}

// The test of the sample for a parameter given by its external ID.
export function testOf(sample, parameter) {
  return refAs(HEAD, parameter).then(({ id }) => sample.tests.find((test) => test.parameterId === id));
}

// The head of department assigns the sample's testing tasks to a person through the assign dialog.
export function assign(sample, person = PEOPLE.tester) {
  const context = { active_ids: sample.tests.map((test) => test.task.id) };
  return refAs(HEAD, person)
    .then(({ id }) => callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: id }], { context }))
    .then((wizard) => callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }));
}

// The scheduler's recommendation for a test, as its assignee reads it.
export function recommendation(test, login = TESTER) {
  return callAs(login, "medilab.sample.test", "read", [
    [test.id],
    ["recommended_method_id", "recommended_machine_id", "recommended_start", "recommended_end"],
  ]).then(([read]) => read);
}

// The open booking of a test, or null.
export function openBooking(test, login = TESTER) {
  return callAs(
    login,
    "medilab.machine.booking",
    "search_read",
    [
      [
        ["sample_test_id", "=", test.id],
        ["status", "in", ["queued", "scheduled", "in_progress"]],
      ],
    ],
    { fields: BOOKING_FIELDS },
  ).then(([booking]) => (booking ? { ...booking, model: "medilab.machine.booking" } : null));
}

// The tester books the recommended machine and slot, and yields the booking.
export function book(test) {
  callAs(TESTER, "medilab.sample.test", "action_schedule", [[test.id]]);
  return openBooking(test);
}

// A lead test of a received sample, assigned to the tester.
export function assignedLead() {
  return receivedSample().then((sample) => {
    assign(sample);
    return testOf(sample, PARAMETERS.lead).then((test) => ({ sample, test }));
  });
}

// A lead test assigned to the tester and booked on the recommended machine.
export function bookedLead() {
  return assignedLead().then(({ sample, test }) => book(test).then((booking) => ({ sample, test, booking })));
}

// Two bookings of lead tests on the same machine, the first booked first. Three machines run lead, so the fourth
// booking shares a machine with an earlier one.
export function bookedOnOneMachine(bookings = []) {
  return bookedLead().then(({ booking }) => {
    const first = bookings.find((other) => other.machine_id[0] === booking.machine_id[0]);
    if (first) {
      return [first, booking];
    }
    expect(bookings, "bookings on different machines").to.have.length.below(3);
    return bookedOnOneMachine([...bookings, booking]);
  });
}

// A task the head of department gives the tester by hand, planned to start in ten minutes.
export function plannedTask() {
  const now = Date.now();
  return refAs(HEAD, "sol_laboratory.task_type_general").then((type) =>
    refAs(HEAD, PEOPLE.tester).then((person) =>
      refAs(HEAD, "sol_demo.demo_hr_department_chemistry").then((department) => {
        const name = `Kiểm tra cân phân tích ${now}`;
        return callAs(HEAD, "medilab.task", "create", [
          {
            type_id: type.id,
            name,
            assignee_id: person.id,
            department_id: department.id,
            deadline: odooTime(now + 60 * MINUTE),
            planned_start: odooTime(now + 10 * MINUTE),
            planned_end: odooTime(now + 40 * MINUTE),
          },
        ]).then((id) => ({ model: "medilab.task", id, name }));
      }),
    ),
  );
}

// Runs the job that reminds people of what starts within the reminder lead.
export function runReminders() {
  return refAs(ADMINISTRATOR, "sol_laboratory.ir_cron_notifications_remind").then(({ id }) =>
    callAs(ADMINISTRATOR, "ir.cron", "method_direct_trigger", [[id]]),
  );
}

// The scheduling settings as the administrator reads them.
export function settings() {
  return callAs(ADMINISTRATOR, "res.config.settings", "default_get", [["urgency_hours", "safety_margin_days"]]);
}

// The administrator saves these settings, as the settings screen does.
export function saveSettings(values) {
  return callAs(ADMINISTRATOR, "res.config.settings", "create", [values]).then((id) =>
    callAs(ADMINISTRATOR, "res.config.settings", "execute", [[id]]),
  );
}

// The stored system parameters of the scheduling settings; a setting never saved has none.
export function storedSettings() {
  return callAs(ADMINISTRATOR, "ir.config_parameter", "search_read", [[["key", "in", SETTING_KEYS]]], { fields: ["key", "value"] });
}

// Removes a setting's stored value, as the administrator does in the system parameters.
export function forgetSetting(key) {
  return callAs(ADMINISTRATOR, "ir.config_parameter", "search", [[["key", "=", key]]]).then(
    (ids) => ids.length && callAs(ADMINISTRATOR, "ir.config_parameter", "unlink", [ids]),
  );
}

// Puts the scheduling settings back as they were stored, and turns the task reminder back on.
export function restoreSettings(stored = []) {
  SETTING_KEYS.forEach((key) => {
    const parameter = stored.find((read) => read.key === key);
    forgetSetting(key).then(() => parameter && callAs(ADMINISTRATOR, "ir.config_parameter", "create", [{ key, value: parameter.value }]));
  });
  return refAs(ADMINISTRATOR, "sol_laboratory.event_task_reminder").then(({ id }) =>
    callAs(ADMINISTRATOR, "mail.message.subtype", "write", [[id], { enabled: true }]),
  );
}

import { callAs } from "../../../support/odoo";
import { ADMINISTRATOR } from "./setup";

const TASK_FIELDS = [
  "name",
  "status",
  "assignee_id",
  "assigned_by_id",
  "department_id",
  "reassign_reason",
  "planned_start",
  "planned_end",
  "document_id",
  "write_date",
];
const TEST_FIELDS = ["status", "parameter_method_id", "due_date", "outsourcing_suggested", "write_date"];
const BOOKING_FIELDS = [
  "sample_test_id",
  "task_id",
  "status",
  "machine_id",
  "person_id",
  "starts_at",
  "ends_at",
  "calendar_event_id",
  "room_event_ids",
  "write_date",
];
const EVENT_FIELDS = [
  "name",
  "start",
  "stop",
  "active",
  "allday",
  "user_id",
  "partner_ids",
  "location_id",
  "machine_booking_id",
  "step_id",
  "medilab_task_id",
  "alarm_ids",
  "write_date",
];

// A committed graph read as an administrator, independently of what the acting user's screen may hide.
export function scheduleState(tests) {
  const ids = (Array.isArray(tests) ? tests : [tests]).map((test) => test.id);
  const state = {};
  callAs(ADMINISTRATOR, "medilab.sample.test", "read", [ids, TEST_FIELDS]).then((rows) => (state.tests = rows));
  callAs(
    ADMINISTRATOR,
    "medilab.task",
    "search_read",
    [
      [
        ["document_model", "=", "medilab.sample.test"],
        ["document_id", "in", ids],
      ],
    ],
    { fields: TASK_FIELDS, order: "id" },
  ).then((rows) => (state.tasks = rows));
  callAs(ADMINISTRATOR, "medilab.machine.booking", "search_read", [[["sample_test_id", "in", ids]]], {
    fields: BOOKING_FIELDS,
    order: "id",
  }).then((rows) => (state.bookings = rows));
  cy.then(() => {
    const eventIds = state.bookings.flatMap((booking) => [
      ...(booking.calendar_event_id ? [booking.calendar_event_id[0]] : []),
      ...booking.room_event_ids,
    ]);
    const alternatives = [
      ["id", "in", eventIds],
      ["machine_booking_id", "in", state.bookings.map(({ id }) => id)],
      ["medilab_task_id", "in", state.tasks.map(({ id }) => id)],
      ...state.tasks.map(({ name }) => ["name", "ilike", name]),
    ];
    return callAs(ADMINISTRATOR, "calendar.event", "search_read", [[...Array(alternatives.length - 1).fill("|"), ...alternatives]], {
      fields: EVENT_FIELDS,
      order: "id",
      context: { active_test: false },
    });
  }).then((rows) => (state.events = rows));
  cy.then(() => {
    const records = {
      "medilab.sample.test": ids,
      "medilab.task": state.tasks.map(({ id }) => id),
      "medilab.machine.booking": state.bookings.map(({ id }) => id),
      "calendar.event": state.events.map(({ id }) => id),
    };
    const groups = Object.entries(records).map(([model, ids]) => ["&", ["model", "=", model], ["res_id", "in", ids]]);
    return callAs(ADMINISTRATOR, "mail.message", "search_read", [[...Array(groups.length - 1).fill("|"), ...groups.flat()]], {
      fields: ["model", "res_id", "message_type", "subtype_id", "subject", "body", "notification_ids"],
      order: "id",
    });
  }).then((rows) => (state.messages = rows));
  cy.then(() =>
    callAs(ADMINISTRATOR, "mail.notification", "search_read", [[["mail_message_id", "in", state.messages.map(({ id }) => id)]]], {
      fields: ["mail_message_id", "res_partner_id", "notification_type", "notification_status", "is_read"],
      order: "id",
    }),
  ).then((rows) => (state.notifications = rows));
  return cy.then(() => state);
}

export function eventsGone(ids) {
  return callAs(ADMINISTRATOR, "calendar.event", "search_count", [[["id", "in", ids]]], { context: { active_test: false } }).should("eq", 0);
}

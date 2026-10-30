import { callAs, refAs } from "../../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
const HEAD = "demo.head_of_department";
const TESTER = "demo.tester";
export const ADMINISTRATOR = "demo.administrator";
export const BACKUP_PERSON = "sol_demo.demo_person_backup_signer";
export const HEAD_ROLE = "sol_demo.demo_role_head_of_department";

// Today in the laboratory, as Odoo stores a date.
export function today() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
}

// Takes every role the deputy head holds until a date away, so each test gives the head's role again.
export function clearBackup() {
  return refAs(ADMINISTRATOR, BACKUP_PERSON).then(({ id }) =>
    callAs(ADMINISTRATOR, "medilab.role.grant", "search", [[["person_id", "=", id]]]).then(
      (ids) => ids.length && callAs(ADMINISTRATOR, "medilab.role.grant", "unlink", [ids]),
    ),
  );
}

// The administrator gives the deputy head the head of department's role until today.
export function giveBackup() {
  return refAs(ADMINISTRATOR, BACKUP_PERSON).then((person) =>
    refAs(ADMINISTRATOR, HEAD_ROLE).then((role) =>
      callAs(ADMINISTRATOR, "medilab.role.grant", "create", [{ person_id: person.id, role_id: role.id, date_end: today() }]),
    ),
  );
}

// A lead result the tester entered on a received bottled water sample, which Chemistry tests; sent when `sent`.
export function enteredResult({ sent = false } = {}) {
  const ids = {};
  refAs(RECEPTION, "sol_demo.demo_customer_an_phu").then(({ id }) => (ids.customer = id));
  refAs(RECEPTION, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (ids.sampleType = id));
  refAs(RECEPTION, "sol_demo.demo_test_parameter_lead").then(({ id }) => (ids.parameter = id));
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
                customer_sample_name: `Nước khoáng ký dự phòng ${Date.now()}`,
                sample_type_id: ids.sampleType,
                physical_state: "liquid",
                test_ids: [[0, 0, { parameter_id: ids.parameter }]],
              },
            ],
          ],
        },
      ]),
    )
    .then((requestId) => {
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[requestId]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", requestId]]], {
        fields: ["test_ids"],
      });
    })
    .then(([sample]) => {
      ids.test = sample.test_ids[0];
      callAs(RECEPTION, "medilab.sample", "action_receive", [[sample.id], "1 chai", "good"]);
      return callAs(ADMINISTRATOR, "medilab.task", "search", [
        [
          ["document_model", "=", "medilab.sample.test"],
          ["document_id", "=", ids.test],
        ],
      ]);
    })
    .then((tasks) => {
      const context = { active_ids: tasks };
      return callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: ids.tester }], { context }).then((wizard) =>
        callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
      );
    })
    .then(() => callAs(TESTER, "medilab.test.result", "create", [{ sample_test_id: ids.test, value: 0.004 }]))
    .then((id) => {
      const result = { model: "medilab.test.result", id };
      if (!sent) {
        return result;
      }
      return callAs(TESTER, "medilab.test.result", "action_sign", [[id]]).then(() => result);
    });
}

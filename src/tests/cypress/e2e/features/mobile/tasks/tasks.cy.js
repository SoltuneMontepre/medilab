import { randomId, refAs, signIn } from "../../../../support/odoo";

const TESTER = "demo.tester";
const SECOND_TESTER = "demo.chemistry_tester";
const HEAD = "demo.head_of_department";
const API = "/medilab/api/v1";

// A phone of the person signed in as Medilab Mobile signs it in, as a new installation. Yields its device key.
function signedInPhone(login) {
  return cy
    .env(["demoPassword"])
    .then(({ demoPassword }) =>
      cy.request("POST", `${API}/sign-in`, {
        login,
        password: demoPassword,
        client_uid: randomId(),
        name: `Pixel ${Date.now()}`,
        platform: "android",
      }),
    )
    .its("body.key");
}

function onPhone(key, method, path, body, headers = {}) {
  return cy.request({
    method,
    url: `${API}${path}`,
    headers: { Authorization: `Bearer ${key}`, ...headers },
    body,
    failOnStatusCode: false,
  });
}

// A task the head of Chemistry creates on the phone and puts in Chemistry's queue, as one a sample would wait in.
function queuedTask(name) {
  return refAs(HEAD, "sol_demo.demo_person_head_of_department").then(({ id: headId }) =>
    refAs(HEAD, "sol_demo.demo_hr_department_chemistry").then(({ id: chemistryId }) =>
      signedInPhone(HEAD).then((headKey) => {
        const deadline = new Date(Date.now() + 2 * 24 * 3600 * 1000).toISOString();
        return onPhone(headKey, "POST", "/tasks", { name, assignee_id: headId, deadline }, { "Idempotency-Key": randomId() })
          .then(({ status, body: task }) => {
            expect(status).to.eq(200);
            const path = `/tasks/${task.id}/assign`;
            onPhone(headKey, "POST", path, { department_id: chemistryId, assignee_id: null }).then(({ status: refused, body }) => {
              expect(refused).to.eq(409);
              expect(body.error.code).to.eq("action_refused");
            });
            onPhone(headKey, "POST", path, { department_id: chemistryId, assignee_id: null, reason: "Whoever is free today" })
              .its("status")
              .should("be.oneOf", [200, 204]);
            return cy.wrap(task);
          });
      }),
    ),
  );
}

describe("Medilab Mobile tasks on the web", () => {
  it("TC-F516-A1 shows a task claimed on the phone as claimed on the web, and refuses the second claim", () => {
    const name = `Check the fridge temperature log ${randomId()}`;
    queuedTask(name).then((task) => {
      signedInPhone(TESTER).then((key) => {
        onPhone(key, "GET", "/tasks?list=queue").its("body.tasks").should("satisfy", (tasks) => tasks.some(({ id }) => id === task.id));
        onPhone(key, "POST", `/tasks/${task.id}/claim`).then(({ status, body }) => {
          expect(status).to.eq(200);
          expect(body.status).to.eq("assigned");
        });
        onPhone(key, "GET", "/tasks?list=open").its("body.tasks").should("satisfy", (tasks) => tasks.some(({ id }) => id === task.id));
      });
      signedInPhone(SECOND_TESTER).then((key) => {
        onPhone(key, "POST", `/tasks/${task.id}/claim`).then(({ status, body }) => {
          expect(status).to.eq(409);
          expect(body.error.code).to.eq("already_claimed");
        });
      });

      signIn(TESTER);
      cy.visit("/odoo/my-tasks");
      cy.contains(".o_data_row", name).should("be.visible");
      signIn(SECOND_TESTER);
      cy.visit("/odoo/awaiting-tasks");
      cy.get(".o_list_view").should("be.visible");
      cy.contains(".o_data_row", name).should("not.exist");
    });
  });
});

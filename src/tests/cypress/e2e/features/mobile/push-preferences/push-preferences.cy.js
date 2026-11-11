import { call, randomId, signIn } from "../../../../support/odoo";

const TESTER = "demo.tester";
const API = "/medilab/api/v1";
const EVENT = "task.reminder";

// A phone of demo.tester signed in as Medilab Mobile signs it in, as a new installation. Yields its device key.
function signedInPhone() {
  return cy
    .env(["demoPassword"])
    .then(({ demoPassword }) =>
      cy.request("POST", `${API}/sign-in`, {
        login: TESTER,
        password: demoPassword,
        client_uid: randomId(),
        name: `Pixel ${Date.now()}`,
        platform: "android",
      }),
    )
    .its("body.key");
}

function onPhone(key, method, path, body) {
  return cy.request({
    method,
    url: `${API}${path}`,
    headers: { Authorization: `Bearer ${key}` },
    body,
    failOnStatusCode: false,
  });
}

function setPush(key, push) {
  return onPhone(key, "PUT", `/notification-preferences/${EVENT}`, { push }).then(({ status, body }) => {
    expect(status).to.eq(200);
    expect(body).to.include({ event: EVENT, push });
  });
}

describe("Medilab Mobile notifications on the web", () => {
  it("TC-F515-A4 shows a push turned off on the phone in the web's notification preferences", () => {
    signedInPhone().then((key) => {
      setPush(key, false);

      signIn(TESTER);
      call("mail.message.subtype", "search_read", [[["code", "=", EVENT]]], { fields: ["name"] }).then(([event]) => {
        cy.visit("/odoo/notification-preferences");
        cy.contains(".o_data_row", event.name).find("[name=enabled] input").should("not.be.checked");

        setPush(key, true);
        cy.reload();
        cy.contains(".o_data_row", event.name).find("[name=enabled] input").should("be.checked");
      });

      onPhone(key, "PUT", "/notification-preferences/test_result.rejected", { push: false }).then(
        ({ status, body }) => {
          expect(status).to.eq(422);
          expect(body.error.code).to.eq("mandatory_event");
        },
      );
    });
  });

  it("TC-F515-A1 opens a notification's document, and says when the person can no longer see it", () => {
    signedInPhone().then((key) => {
      onPhone(key, "GET", "/notifications").then(({ body }) => {
        // demo.tester's reminders: read and unread, one about a task that went to another tester.
        const reminders = body.notifications.filter((notification) => notification.event === EVENT);
        expect(reminders.map((notification) => notification.read)).to.include.members([true, false]);
        const statuses = [];
        reminders.forEach(({ document }) => {
          onPhone(key, "GET", `/documents/${document.model}/${document.id}`).then(({ status }) => statuses.push(status));
        });
        cy.wrap(statuses).should("include", 200).and("include", 404);
      });
    });
  });
});

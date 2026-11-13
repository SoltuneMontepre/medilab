import { randomId, refAs, signIn } from "../../../../support/odoo";

const TESTER = "demo.tester";
const HEAD = "demo.head_of_department";
const RECEPTION = "demo.sample_delivery_staff";
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

function onPhone(key, method, path, body) {
  return cy.request({
    method,
    url: `${API}${path}`,
    headers: { Authorization: `Bearer ${key}` },
    body,
    failOnStatusCode: false,
  });
}

describe("Medilab Mobile scanning on the web", () => {
  it("TC-F517-A1 shows the receipt scanned on the phone on the web, and offers only the tester's department tasks", () => {
    refAs(HEAD, "sol_demo.demo_sample_label_scan").then(({ id: sampleId }) => {
      refAs(HEAD, "sol_demo.demo_task_sample_test_label_scan_lead").then(({ id: leadTaskId }) => {
        signedInPhone(TESTER).then((key) => {
          onPhone(key, "GET", `/samples/${sampleId}`).then(({ status, body: sample }) => {
            expect(status).to.eq(200);
            expect(sample.customer).to.eq(null);
            expect(sample.tasks.map(({ id }) => id)).to.deep.eq([leadTaskId]);

            signedInPhone(RECEPTION).then((receptionKey) => {
              onPhone(receptionKey, "POST", "/samples/receive", { code: sample.code }).then(({ status: refused, body }) => {
                expect(refused).to.eq(409);
                expect(body.error.code).to.eq("action_refused");
                expect(body.error.message).to.contain(sample.code);
              });
            });

            onPhone(key, "POST", "/samples/receive", { code: sample.code }).then(({ status: receivedStatus, body: received }) => {
              expect(receivedStatus).to.eq(200);
              expect(received.handover.received_at).to.be.a("string");
              const receivedBy = received.handover.received_by;

              signIn(HEAD);
              cy.visit(`/odoo/medilab.sample/${sampleId}`);
              cy.get(".o_notebook .nav-link[name=handovers]").click();
              cy.contains('.o_field_widget[name="handover_ids"] .o_data_row', received.handover.department)
                .should("contain", receivedBy);
            });
          });
        });
      });
    });
  });
});

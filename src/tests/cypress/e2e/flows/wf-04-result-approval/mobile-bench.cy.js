import { randomId, signIn } from "../../../support/odoo";
import { HEAD, TESTER, assignedTest } from "./setup";

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

// The result the tester enters for the test on the phone and signs from the confirmation step. Yields the result.
function signedOnPhone(test) {
  return signedInPhone(TESTER).then((key) =>
    onPhone(key, "GET", `/sample-tests/${test.id}`).then(({ status, body: sampleTest }) => {
      expect(status).to.eq(200);
      expect(sampleTest.can_enter_result).to.eq(true);
      const entry = { value: 0.008, ...(sampleTest.comparison_requested ? { conclusion: "pass" } : {}) };
      return onPhone(key, "POST", `/sample-tests/${test.id}/results`, entry, { "Idempotency-Key": randomId() }).then(
        ({ status: entered, body: result }) => {
          expect(entered).to.eq(200);
          onPhone(key, "POST", `/results/${result.id}/sign`, { confirmed: false }).its("status").should("eq", 400);
          const signature = { confirmed: true, ...(result.warnings.length ? { warnings_acknowledged: true } : {}) };
          return onPhone(key, "POST", `/results/${result.id}/sign`, signature).then(({ status: signed, body }) => {
            expect(signed).to.eq(200);
            expect(body.status).to.eq("requested");
            expect(body.actions).to.deep.eq({ edit: false, sign: false, reject: false });
            return body;
          });
        },
      );
    }),
  );
}

describe("WF-04 Medilab Mobile testing at the bench on the web", () => {
  it("TC-F518-A1 shows a result signed on the phone waiting for the head with the tester's signature", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      signedOnPhone(test).then((result) => {
        signedInPhone(HEAD).then((key) => {
          onPhone(key, "GET", "/results?awaiting=me&limit=100")
            .its("body.results")
            .should("satisfy", (results) => results.some(({ id }) => id === result.id));
          onPhone(key, "POST", `/results/${result.id}/reject`, { reason: "   " }).then(({ status, body }) => {
            expect(status).to.eq(409);
            expect(body.error.code).to.eq("action_refused");
          });
        });

        signIn(HEAD);
        cy.visit(`/odoo/medilab.test.result/${result.id}`);
        cy.get(".o_statusbar_status button[data-value=requested]").should("have.class", "o_arrow_button_current");
        cy.get('.o_statusbar_buttons button[name="action_sign"]:visible').should("have.length", 1);
        cy.get(".o_notebook .nav-link[name=signatures]").click();
        cy.contains('.o_field_widget[name="signature_ids"] .o_data_row', result.entered_by).should("be.visible");
      });
    });
  });
});

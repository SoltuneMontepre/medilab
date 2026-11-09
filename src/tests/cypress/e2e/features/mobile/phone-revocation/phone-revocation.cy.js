import { call, randomId, signIn } from "../../../../support/odoo";

const TESTER = "demo.tester";
const ADMINISTRATOR = "demo.administrator";
const API = "/medilab/api/v1";

// A phone of demo.tester signed in as Medilab Mobile signs it in, as a new installation, with its push token
// registered. Yields what the app keeps: the installation id, the device key and the token.
function signedInPhone(name) {
  const phone = { clientUid: randomId(), token: `cypress-${randomId()}` };
  return cy
    .env(["demoPassword"])
    .then(({ demoPassword }) =>
      cy.request("POST", `${API}/sign-in`, {
        login: TESTER,
        password: demoPassword,
        client_uid: phone.clientUid,
        name,
        platform: "android",
      }),
    )
    .then(({ body }) => {
      phone.key = body.key;
      return cy.request({
        method: "PUT",
        url: `${API}/push-token`,
        headers: { Authorization: `Bearer ${phone.key}` },
        body: { token: phone.token },
      });
    })
    .then(({ status }) => {
      expect(status).to.eq(204);
      return phone;
    });
}

function modulesWith(key) {
  return cy.request({
    url: `${API}/modules`,
    headers: { Authorization: `Bearer ${key}` },
    failOnStatusCode: false,
  });
}

describe("Medilab Mobile phones on the web", () => {
  it("TC-F514-A3 lets an administrator revoke a phone, which is refused at its next call and gets no more pushes", () => {
    const name = `Pixel ${Date.now()}`;
    signedInPhone(name).then((phone) => {
      modulesWith(phone.key).its("body.modules").should("include", "sol_laboratory");

      signIn(ADMINISTRATOR);
      cy.visit("/odoo/laboratory-devices");
      cy.contains(".o_data_row", name).find("button[name=action_revoke]").click();
      cy.get(".modal-footer .btn-primary").click();
      cy.contains(".o_data_row", name).find("button[name=action_revoke]").should("not.exist");

      modulesWith(phone.key).then(({ status, body }) => {
        expect(status).to.eq(401);
        expect(body.error.code).to.eq("invalid_key");
      });
      call("medilab.mobile.device", "search_read", [[["token", "=", phone.token]]], {
        fields: ["active"],
        context: { active_test: false },
      }).then((tokens) => expect(tokens.map((token) => token.active)).to.deep.equal([false]));
    });
  });
});

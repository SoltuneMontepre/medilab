// What the browser tests do in Odoo as a demo user: sign in, and call a model method in the signed-in session.
const PASSWORD = "demo";

export function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

export function call(model, method, args, kwargs = {}) {
  return cy
    .request("POST", `/web/dataset/call_kw/${model}/${method}`, {
      jsonrpc: "2.0",
      method: "call",
      params: { model, method, args, kwargs },
    })
    .then(({ body }) => {
      expect(body.error, JSON.stringify(body.error)).to.be.undefined;
      return body.result;
    });
}

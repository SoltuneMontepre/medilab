export function signIn(login) {
  return cy.env(["demoPassword"]).then(({ demoPassword }) => {
    cy.session([Cypress.config("baseUrl"), login], () => {
      cy.visit("/web/login");
      cy.get("input[name=login]").type(login);
      cy.get("input[name=password]").type(demoPassword, {
        log: false,
        parseSpecialCharSequences: false,
      });
      cy.get("form.oe_login_form").submit();
      cy.location("pathname").should("match", /^\/(odoo|my)(\/|$)/);
    }, {
      cacheAcrossSpecs: false,
      validate() {
        cy.request("POST", "/web/session/get_session_info", {
          jsonrpc: "2.0",
          method: "call",
          params: {},
        }).its("body.result.username").should("eq", login);
      },
    });
    cy.visit("/web");
    return cy.location("pathname").should("match", /^\/(odoo|my)(\/|$)/);
  });
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

export function resolveRecord(xmlId) {
  const parts = xmlId.split(".");
  expect(parts, "external ID in module.name form").to.have.length(2);
  expect(parts.every(Boolean), "external ID has a module and a name").to.be.true;
  return call("ir.model.data", "check_object_reference", parts).then(([model, id]) => {
    expect(model, "external ID model").to.be.a("string").and.not.be.empty;
    expect(id, "external ID record").to.be.a("number").and.be.greaterThan(0);
    return { model, id };
  });
}

export function readRecord(xmlId, fields) {
  expect(fields, "fields to compare").to.be.an("array").and.not.be.empty;
  return resolveRecord(xmlId)
    .then(({ model, id }) => call(model, "read", [[id], fields]))
    .then((records) => {
      expect(records, "readable record").to.have.length(1);
      return records[0];
    });
}

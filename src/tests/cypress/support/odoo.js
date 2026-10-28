// The backend's service worker checks for an update after its page has gone. Sent after the session is
// cleared, that request gets a new session cookie, which the login form's CSRF token no longer matches.
// Unregistering waits for an update in progress and cancels later ones.
function removeServiceWorkers() {
  return cy.then(() =>
    navigator.serviceWorker?.getRegistrations().then((registrations) => Promise.all(registrations.map((registration) => registration.unregister()))),
  );
}

export function signIn(login) {
  return cy.env(["demoPassword"]).then(({ demoPassword }) => {
    removeServiceWorkers();
    cy.session(
      [Cypress.config("baseUrl"), login],
      () => {
        cy.visit("/web/login");
        cy.get("input[name=login]").type(login);
        cy.get("input[name=password]").type(demoPassword, {
          log: false,
          parseSpecialCharSequences: false,
        });
        cy.get("form.oe_login_form").submit();
        cy.location("pathname").should("match", /^\/(odoo|my)(\/|$)/);
      },
      {
        cacheAcrossSpecs: false,
        validate() {
          cy.request("POST", "/web/session/get_session_info", {
            jsonrpc: "2.0",
            method: "call",
            params: {},
          })
            .its("body.result.username")
            .should("eq", login);
        },
      },
    );
    cy.visit("/web");
    return cy.location("pathname").should("match", /^\/(odoo|my)(\/|$)/);
  });
}

// A call carries the signed-in user's context, so its messages are in the user's language, as on screen.
function callKw(model, method, args, kwargs) {
  return cy
    .request("POST", "/web/session/get_session_info", { jsonrpc: "2.0", method: "call", params: {} })
    .its("body.result.user_context", { log: false })
    .then((context) =>
      cy.request("POST", `/web/dataset/call_kw/${model}/${method}`, {
        jsonrpc: "2.0",
        method: "call",
        params: { model, method, args, kwargs: { ...kwargs, context: { ...context, ...kwargs.context } } },
      }),
    );
}

export function call(model, method, args, kwargs = {}) {
  return callKw(model, method, args, kwargs).then(({ body }) => {
    expect(body.error, JSON.stringify(body.error)).to.be.undefined;
    return body.result;
  });
}

// Calls a model method that must be refused, and yields the server's message.
export function callRefused(model, method, args, kwargs = {}) {
  return callKw(model, method, args, kwargs).then(({ body }) => {
    expect(body.error, `${model}.${method} refused`).to.exist;
    return body.error.data.message;
  });
}

// Execution metadata identifies pending work without exposing RPC arguments or session cookies.
export function task(name, payload, options) {
  const execution = Cypress.expose("wf03Execution");
  return cy.task(
    name,
    execution
      ? {
          ...payload,
          execution: {
            ...execution,
            callId: crypto.randomUUID(),
            test: Cypress.currentTest?.titlePath.join(" > ") || "suite hook",
          },
        }
      : payload,
    options,
  );
}

// Calls a model method as another login from the test runner, leaving the browser's session as it is.
export function callAs(login, model, method, args, kwargs = {}) {
  return task("odooCall", { login, model, method, args, kwargs });
}

// A record given by its external ID, resolved as another login from the test runner.
export function refAs(login, xmlId, kwargs = {}) {
  return callAs(login, "ir.model.data", "check_object_reference", xmlId.split("."), kwargs).then(([model, id]) => ({ model, id }));
}

// Posts a portal form as another login from the test runner, with the CSRF token of the page that shows it.
export function portalPostAs(login, page, path, form = {}) {
  return cy.task("odooPortalPost", { login, page, path, form });
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

// A record given by its external ID, or already as `{ model, id }`.
export function recordRef(record) {
  return typeof record === "string" ? resolveRecord(record) : cy.wrap(record, { log: false });
}

export function readRecord(record, fields) {
  expect(fields, "fields to compare").to.be.an("array").and.not.be.empty;
  return recordRef(record)
    .then(({ model, id }) => call(model, "read", [[id], fields]))
    .then((records) => {
      expect(records, "readable record").to.have.length(1);
      return records[0];
    });
}

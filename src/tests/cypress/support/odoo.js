// While a quiet helper runs, the requests and checks inside it stay out of the Command Log.
let quiet = 0;
export const logged = () => quiet === 0;
export const beginQuiet = () => (quiet += 1);
export const endQuiet = () => (quiet -= 1);
export const resetQuiet = () => (quiet = 0);

// One line of the Command Log for a model method call, as `login: model.method`.
function rpcLine(model, method, login) {
  if (logged()) Cypress.log({ name: "rpc", message: login ? `${login}: ${model}.${method}` : `${model}.${method}` });
}

export function signIn(login) {
  return cy.env(["demoPassword"], { log: false }).then(({ demoPassword }) => {
    cy.session(
      [Cypress.config("baseUrl"), login],
      () => {
        cy.request({ url: "/web/login", log: false }).then(({ body }) => {
          const page = new DOMParser().parseFromString(body, "text/html");
          const csrfToken = page.querySelector("input[name=csrf_token]")?.value;
          expect(csrfToken, "login CSRF token").to.be.a("string").and.not.be.empty;
          return cy.request({
            method: "POST",
            url: "/web/login",
            form: true,
            followRedirect: false,
            log: false,
            body: { login, password: demoPassword, csrf_token: csrfToken },
          }).its("status").should("be.oneOf", [302, 303]);
        });
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
    cy.visit("/web", { log: logged() });
    return cy.location("pathname", { log: logged() }).should("match", /^\/(odoo|my)(\/|$)/);
  });
}

// Sign out through Odoo so in-flight page requests cannot race to initialize a session after clearing cookies.
export function becomeVisitor() {
  return cy.request({ url: "/catalog", log: false }).then(({ body }) => {
    const catalog = new DOMParser().parseFromString(body, "text/html");
    const csrfToken = catalog.querySelector("input[name=csrf_token]")?.value;
    expect(csrfToken, "catalog CSRF token").to.be.a("string").and.not.be.empty;
    cy.request({
      method: "POST",
      url: "/web/session/logout",
      form: true,
      followRedirect: false,
      body: { csrf_token: csrfToken, redirect: "/catalog" },
      log: false,
    }).its("status").should("eq", 303);
    return cy.visit("/catalog");
  });
}

// A call carries the signed-in user's context, so its messages are in the user's language, as on screen.
function callKw(model, method, args, kwargs) {
  return cy
    .then(() => {
      rpcLine(model, method);
      return cy
        .request({ method: "POST", url: "/web/session/get_session_info", body: { jsonrpc: "2.0", method: "call", params: {} }, log: false })
        .its("body.result.user_context", { log: false });
    })
    .then((context) =>
      cy.request({
        method: "POST",
        url: `/web/dataset/call_kw/${model}/${method}`,
        body: {
          jsonrpc: "2.0",
          method: "call",
          params: { model, method, args, kwargs: { ...kwargs, context: { ...context, ...kwargs.context } } },
        },
        log: false,
      }),
    );
}

export function call(model, method, args, kwargs = {}) {
  return callKw(model, method, args, kwargs).then(({ body }) => {
    if (body.error !== undefined) expect(body.error, JSON.stringify(body.error)).to.be.undefined;
    return body.result;
  });
}

// Calls a model method that must be refused, and yields the server's message.
export function callRefused(model, method, args, kwargs = {}) {
  return callKw(model, method, args, kwargs).then(({ body }) => {
    if (!body.error) expect(body.error, `${model}.${method} refused`).to.exist;
    return body.error.data.message;
  });
}

// A random identifier. crypto.randomUUID needs a secure origin, which an HTTP address other than localhost is not.
export function randomId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
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
            callId: randomId(),
            test: Cypress.currentTest?.titlePath.join(" > ") || "suite hook",
          },
        }
      : payload,
    options,
  );
}

// Calls a model method as another login from the test runner, leaving the browser's session as it is.
export function callAs(login, model, method, args, kwargs = {}) {
  return cy.then(() => {
    rpcLine(model, method, login);
    return task("odooCall", { login, model, method, args, kwargs }, { log: false });
  });
}

// A record given by its external ID, resolved as another login from the test runner.
export function refAs(login, xmlId, kwargs = {}) {
  return callAs(login, "ir.model.data", "check_object_reference", xmlId.split("."), kwargs).then(([model, id]) => ({ model, id }));
}

// Posts a portal form as another login from the test runner, with the CSRF token of the page that shows it.
export function portalPostAs(login, page, path, form = {}) {
  return cy.task("odooPortalPost", { login, page, path, form });
}

// The checks of these helpers show in the Command Log only when they fail.
export function resolveRecord(xmlId) {
  const parts = xmlId.split(".");
  if (parts.length !== 2 || !parts.every(Boolean)) expect(parts, "external ID in module.name form").to.have.length(2).and.not.include("");
  return call("ir.model.data", "check_object_reference", parts).then(([model, id]) => {
    if (typeof model !== "string" || !model) expect(model, "external ID model").to.be.a("string").and.not.be.empty;
    if (typeof id !== "number" || id <= 0) expect(id, "external ID record").to.be.a("number").and.be.greaterThan(0);
    return { model, id };
  });
}

// A record given by its external ID, or already as `{ model, id }`.
export function recordRef(record) {
  return typeof record === "string" ? resolveRecord(record) : cy.wrap(record, { log: false });
}

export function readRecord(record, fields) {
  if (!Array.isArray(fields) || !fields.length) expect(fields, "fields to compare").to.be.an("array").and.not.be.empty;
  return recordRef(record)
    .then(({ model, id }) => call(model, "read", [[id], fields]))
    .then((records) => {
      if (records.length !== 1) expect(records, "readable record").to.have.length(1);
      return records[0];
    });
}

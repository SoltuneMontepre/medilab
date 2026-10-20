const PASSWORD = "demo";
const WORKSHEET = "tinh-toan-nong-do-Pb.csv";
const LOCK_ACTION = "Lock the worksheet as the tester";

// Locking is done by Medilab Sync through the laboratory files API, which Odoo's RPC does not reach; a server action
// takes the lock as the demo tester, as the API would, so the test does not depend on the seeded lock still holding.
// It is an action of server actions, as running an action needs the right to change records of its model.
const LOCK_AS_TESTER = `
tester = env.ref("sol_demo.demo_res_users_tester")
worksheet = env.ref("sol_demo.demo_laboratory_file_concentration").with_user(tester)
worksheet._lock(env.ref("sol_demo.demo_laboratory_device_hplc_pc"))
`;

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

function call(model, method, args, kwargs = {}) {
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

// Signs the administrator in with requests only, so no open page keeps their session once the test signs someone in.
function signInAsAdministrator() {
  cy.request("/web/login").then(({ body }) => {
    const csrfToken = /name="csrf_token" value="([^"]+)"/.exec(body)[1];
    cy.request({ method: "POST", url: "/web/login", form: true, body: { login: "demo.administrator", password: PASSWORD, csrf_token: csrfToken } });
  });
}

function lockWorksheetAsTester() {
  signInAsAdministrator();
  call("ir.model", "search", [[["model", "=", "ir.actions.server"]]]).then(([modelId]) =>
    call("ir.actions.server", "create", [{ name: LOCK_ACTION, model_id: modelId, state: "code", code: LOCK_AS_TESTER }]).then((actionId) =>
      call("ir.actions.server", "run", [[actionId]]),
    ),
  );
  cy.clearAllCookies();
}

// Leaves the test's page for the sign-in page, whose session the requests then share.
function deleteLockAction() {
  cy.clearAllCookies();
  cy.visit("/web/login");
  signInAsAdministrator();
  call("ir.actions.server", "search", [[["name", "=", LOCK_ACTION]]]).then((actionIds) => call("ir.actions.server", "unlink", [actionIds]));
  cy.clearAllCookies();
}

describe("Laboratory file locks", () => {
  afterEach(deleteLockAction);

  it("shows a tester's lock to the other members of its folder, without the release button", () => {
    lockWorksheetAsTester();
    signIn("demo.chemistry_tester");
    cy.visit("/odoo/laboratory-file-locks");

    cy.contains(".o_data_row", WORKSHEET).should("be.visible");
    cy.get("button[name=action_release]").should("not.exist");
  });

  it("lets an administrator release a lock a tester left", () => {
    lockWorksheetAsTester();
    signIn("demo.administrator");
    cy.visit("/odoo/laboratory-file-locks");

    cy.contains(".o_data_row", WORKSHEET).find("button[name=action_release]").click();

    cy.contains(".o_data_row", WORKSHEET).should("not.exist");
  });
});

// Accepts the demo certificate, so it passes once per database; CI installs a fresh one for every run.
const PASSWORD = "demo";
const ORGANISATION = "Phòng Thí nghiệm Kiểm nghiệm Medilab";
const CERTIFICATE = "VILAS 9901";

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

// Cypress's browser grants notifications, so Odoo subscribes to push messages, fails and covers the stat buttons with
// the error.
Cypress.on("window:before:load", (win) => {
  Object.defineProperty(win.Notification, "permission", { get: () => "default" });
});

// The demo keeps a run running, which would refuse starting another.
function cancelRunningRuns() {
  call("medilab.onboarding.run", "search", [[["state", "=", "running"]]]).then((runIds) => {
    if (runIds.length) {
      call("medilab.onboarding.run", "action_cancel", [runIds]);
    }
  });
}

function currentStatus() {
  return cy.get(".o_statusbar_status .o_arrow_button_current");
}

describe("Onboarding", () => {
  it("lets an administrator run a collection, accept a certificate with its methods and open its origin", () => {
    signIn("demo.administrator");
    cancelRunningRuns();

    cy.intercept("POST", "/web/dataset/call_kw/medilab.onboarding.organisation/web_name_search").as("organisations");
    cy.visit("/odoo/onboarding-runs");
    cy.get(".o_list_button_add").click();
    cy.get(".o_field_widget[name=organisation_id] input").click();
    cy.wait("@organisations").its("response.body.result.0.display_name").should("eq", ORGANISATION);
    cy.contains(".o-autocomplete--dropdown-item", ORGANISATION).click();
    cy.get("button[name=action_start]").click();
    // Demo sources are turned off, so the run has nothing to fetch.
    currentStatus().should("contain", "Done");

    cy.visit("/odoo/staged-records");
    cy.contains(".o_group_name", "Certificate").click();
    cy.contains(".o_data_row", CERTIFICATE).click();
    cy.get("button[name=action_accept]").click();
    cy.get(".modal .o_field_widget[name=field_id] input").type("Chemistry");
    cy.contains(".o-autocomplete--dropdown-item", "Chemistry").click();
    cy.get(".modal button[name=action_confirm]").click();
    currentStatus().should("contain", "Accepted");

    cy.visit("/odoo/accreditation-certificates");
    cy.contains(".o_data_row", CERTIFICATE).click();
    cy.get(".o_field_widget[name=method_ids]").within(() => {
      for (const code of ["TCVN 6492:2011", "TCVN 8126:2009", "TCVN 6658:2000"]) {
        cy.contains(".o_data_row", code).should("be.visible");
      }
    });
    cy.get("button[name=action_open_onboarding_origin]").click();
    cy.contains(".o_data_row", "https://www.boa.gov.vn/vi/timkiem/tochuc/9901").click();

    cy.get(".o_field_widget[name=external_key] input").should("have.value", CERTIFICATE);
  });
});

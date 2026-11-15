// Accepts the demo certificate, so it passes once per database; CI installs a fresh one for every run.
import { newRecord } from "../../../../support/form";
import { call } from "../../../../support/odoo";

const ORGANISATION = "Phòng Thí nghiệm Kiểm nghiệm Medilab";
const CERTIFICATE = "VILAS 9901";

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
  it("TC-F176: an administrator runs a collection, accepts a certificate's methods into the catalog and opens its origin", () => {
    cy.signInAs("administrator");
    cancelRunningRuns();

    newRecord("/odoo/onboarding-runs");
    cy.intercept("POST", "/web/dataset/call_kw/medilab.onboarding.organisation/web_name_search").as("organisations");
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

    // The methods go into the catalog; the administrator adds the certificate's scope lines by hand.
    const codes = ["TCVN 6492:2011", "TCVN 6658:2000", "TCVN 8126:2009"];
    call("medilab.testing.method", "search_read", [[["code", "in", codes]]], { fields: ["code"] }).then((methods) => {
      expect(methods.map(({ code }) => code).sort()).to.deep.equal(codes);
    });
    cy.visit("/odoo/accreditation-certificates");
    cy.contains(".o_data_row", CERTIFICATE).click();
    cy.get(".o_field_widget[name=scope_line_ids] .o_data_row").should("not.exist");
    cy.get("button[name=action_open_onboarding_origin]").click();
    cy.contains(".o_data_row", "https://www.boa.gov.vn/vi/timkiem/tochuc/9901").click();

    cy.get(".o_field_widget[name=external_key]").should("have.text", CERTIFICATE);
  });
});

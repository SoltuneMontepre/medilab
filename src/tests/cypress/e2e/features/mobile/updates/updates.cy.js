import { callAs } from "../../../../support/odoo";

const ADMINISTRATOR = "demo.administrator";
const SETTINGS = ["mobile_minimum_version", "mobile_stopped_versions"];
// The runtime of the demo releases in sol_demo's catalog: 1.0.0, 1.1.0, stopped as rolled back, and 1.1.1.
const RUNTIME = "7b045729655462c0c9ff57ceb72d3ed02d9ec17c";

function served() {
  return callAs(ADMINISTRATOR, "res.config.settings", "default_get", [SETTINGS]);
}

function serve(values) {
  return callAs(ADMINISTRATOR, "res.config.settings", "create", [values]).then((id) =>
    callAs(ADMINISTRATOR, "res.config.settings", "execute", [[id]]),
  );
}

// What MediLab tells a phone running the version on the demo runtime, as the app asks at start.
function releaseFor(version, runtime = RUNTIME) {
  return cy.request({ url: `/medilab/api/v1/mobile/release/android/${runtime}/${version}`, failOnStatusCode: false });
}

function setting(name) {
  return cy.get(`.o_field_widget[name=${name}] input`);
}

describe("Medilab Mobile updates", () => {
  let stored;
  beforeEach(() => served().then((values) => (stored = values)));
  afterEach(() =>
    serve({ mobile_minimum_version: stored.mobile_minimum_version, mobile_stopped_versions: stored.mobile_stopped_versions }),
  );

  it("TC-F525-A4 sends phones on the rolled-back release to the release that replaces it", () => {
    releaseFor("1.1.0").then(({ status, body }) => {
      expect(status).to.eq(200);
      expect(body).to.deep.eq({ action: "code", version: "1.1.1" });
    });
    releaseFor("1.0.0").its("body").should("deep.equal", { action: "code", version: "1.1.1" });
    releaseFor("1.1.1").its("status").should("eq", 204);
    // A phone of another native build cannot run the code update, so it installs the APK.
    releaseFor("1.0.0", "another-runtime").its("body").should("include", { action: "install", version: "1.1.1" });
  });

  it("TC-F525-A3 lets an administrator stop a release and set the oldest version served", () => {
    cy.signInAs("administrator");
    cy.visit("/odoo/lab-settings");
    cy.contains("h2", "Medilab Mobile").scrollIntoView().should("be.visible");
    setting("mobile_stopped_versions").clear().type("1.1.0, 1.1.1").blur();
    setting("mobile_minimum_version").clear().type("1.1.1").blur();
    cy.intercept("POST", "**/res.config.settings/execute").as("savedSettings");
    cy.get(".o_control_panel .o_form_button_save").click();
    cy.wait("@savedSettings").its("response.body.error").should("not.exist");

    // No release reaches 1.1.1 any more, so a phone on 1.0.0 shows only the updating screen.
    releaseFor("1.0.0").its("body").should("deep.equal", { action: "unavailable" });
    served().should("include", { mobile_minimum_version: "1.1.1", mobile_stopped_versions: "1.1.0, 1.1.1" });

    // The refusal names the value, in the administrator's language.
    cy.expectRefusal({
      read: served,
      action: () => {
        setting("mobile_minimum_version").clear().type("latest").blur();
        cy.get(".o_control_panel .o_form_button_save").click();
      },
      message: "latest",
    });
  });
});

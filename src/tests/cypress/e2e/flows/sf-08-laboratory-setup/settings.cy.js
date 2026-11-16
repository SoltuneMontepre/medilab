import { call, callAs, callRefused } from "../../../support/odoo";
import {
  ADMINISTRATOR,
  PARAMETERS,
  URGENCY,
  checkpointSettings,
  enableReminders,
  forgetSetting,
  receivedSample,
  releaseFixtures,
  resetFixtures,
  restoreSettings,
  saveSettings,
  settings,
  storedSettings,
  testOf,
} from "../wf-03-testing-scheduling/setup";

const time = (value) => new Date(`${value}Z`).getTime();

beforeEach(resetFixtures);
afterEach(releaseFixtures);

describe("SF-08 settings and thresholds (F-22)", () => {
  let stored;
  beforeEach(() => {
    stored = undefined;
    return checkpointSettings().then((snapshot) => {
      stored = snapshot;
      return enableReminders();
    });
  });
  afterEach(() => restoreSettings(stored));

  it("TC-F22-01 rejects malformed urgency on screen, then saves a valid value through Save", () => {
    settings().then(({ urgency_hours: initial }) => {
      cy.signInAs("administrator");
      cy.visit("/odoo/lab-settings");
      const input = ".o_field_widget[name=urgency_hours] input";
      cy.get(input).should("have.value", String(initial)).clear().type("invalid").blur();
      cy.get(".o_control_panel .o_form_button_save").should("be.visible").click();
      cy.get(".o_field_widget[name=urgency_hours]").should("have.class", "o_field_invalid");
      settings().its("urgency_hours").should("eq", initial);
      cy.get(input)
        .clear()
        .type(String(initial + 1))
        .blur();
      cy.intercept("POST", "**/res.config.settings/execute").as("savedSettings");
      cy.intercept("POST", "**/res.config.settings/onchange").as("reloadedSettings");
      cy.get(".o_control_panel .o_form_button_save").click();
      cy.wait("@savedSettings").its("response.body.error").should("not.exist");
      cy.wait("@reloadedSettings")
        .its("response.body.result.value.urgency_hours")
        .should("eq", initial + 1);
      cy.get(input).should("have.value", String(initial + 1));
      settings()
        .its("urgency_hours")
        .should("eq", initial + 1);
    });
  });

  it("TC-F22-01 RPC refuses settings changes by a tester without changing the stored values", () => {
    storedSettings().then((before) => {
      cy.signInAs("tester");
      callRefused("res.config.settings", "create", [{ urgency_hours: 999 }]).should("match", /not allowed|access/i);
      storedSettings().should("deep.equal", before);
    });
  });

  it("TC-F22-02 keeps the due dates already worked out when the safety margin changes", () => {
    receivedSample().then((before) => {
      testOf(before, PARAMETERS.lead).then((test) => callAs(ADMINISTRATOR, "medilab.sample.test", "read", [[test.id], ["due_date"]]).as("due"));
      settings().then(({ safety_margin_days: margin }) => saveSettings({ safety_margin_days: margin + 1 }));
      receivedSample().then((after) => {
        cy.signInAs("head_of_department");
        cy.get("@due").then(([{ due_date: due }]) => {
          testOf(before, PARAMETERS.lead).then((test) => cy.readRecord(test, ["due_date"]).its("due_date").should("eq", due));
          testOf(after, PARAMETERS.lead).then((test) =>
            cy
              .readRecord(test, ["due_date"])
              .its("due_date")
              .should((later) => expect(time(due) - time(later)).to.equal(86400000)),
          );
        });
      });
    });
  });

  it("TC-F22-03 falls back to the default urgency while none is stored, and audits each change", () => {
    forgetSetting(URGENCY);
    cy.signInAs("administrator");
    cy.visit("/odoo/lab-settings");
    cy.get(".o_field_widget[name=urgency_hours] input").should("have.value", "24");
    saveSettings({ urgency_hours: 48 });
    saveSettings({ urgency_hours: 36 });
    settings().its("urgency_hours").should("eq", 36);
    call(
      "medilab.audit.entry",
      "search_read",
      [
        [
          ["document_model", "=", "ir.config_parameter"],
          ["note", "=", URGENCY],
        ],
      ],
      {
        fields: ["action", "user_id"],
        order: "id desc",
        limit: 2,
      },
    ).should((entries) => {
      expect(entries.map((entry) => entry.action)).to.deep.equal(["edit", "create"]);
      entries.forEach((entry) => expect(entry.user_id[1]).to.equal("Phan Minh Quan"));
    });
  });
});

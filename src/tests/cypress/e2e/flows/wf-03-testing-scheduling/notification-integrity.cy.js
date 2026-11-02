import { save } from "../../../support/form";
import { callAs, callRefused, refAs } from "../../../support/odoo";

const ADMINISTRATOR = "demo.administrator";
const MESSAGE = "A mandatory event cannot be turned off.";
const EVENT_FIELDS = ["name", "code", "mandatory", "enabled", "res_model", "recipient_ids", "write_date"];

function snapshot(event) {
  return callAs(ADMINISTRATOR, "mail.message.subtype", "read", [[event.id], EVENT_FIELDS]).then(([read]) =>
    callAs(ADMINISTRATOR, "medilab.notification.event.recipient", "read", [
      read.recipient_ids, ["event_id", "role_id", "department_id", "write_date"],
    ]).then((recipients) => ({ event: read, recipients })),
  );
}

describe("Notification event integrity", () => {
  let mandatory;
  let optional;
  let originalEnabled;

  beforeEach(() => {
    mandatory = null;
    optional = null;
    originalEnabled = undefined;
    cy.signInAs("administrator");
    refAs(ADMINISTRATOR, "sol_laboratory.event_test_result_rejected").then((event) => { mandatory = event; });
    refAs(ADMINISTRATOR, "sol_laboratory.event_task_reminder").then((event) => {
      optional = event;
      return callAs(ADMINISTRATOR, "mail.message.subtype", "read", [[event.id], ["enabled"]]);
    }).then(([event]) => { originalEnabled = event.enabled; });
  });

  afterEach(() => {
    if (optional && originalEnabled !== undefined) {
      callAs(ADMINISTRATOR, "mail.message.subtype", "read", [[optional.id], ["enabled"]]).then(([read]) => {
        if (read.enabled !== originalEnabled) {
          callAs(ADMINISTRATOR, "mail.message.subtype", "write", [[optional.id], { enabled: originalEnabled }]);
        }
        return callAs(ADMINISTRATOR, "mail.message.subtype", "read", [[optional.id], ["enabled"]]);
      }).should(([read]) => expect(read.enabled).to.equal(originalEnabled));
    }
  });

  it("TC-F25-03 keeps mandatory controls read-only and refuses disabling, demotion, code changes and deletion through direct requests", () => {
    cy.then(() => cy.visit(`/odoo/notification-events/${mandatory.id}`));
    cy.get(".o_field_widget[name=enabled] input").should("be.checked").and("be.disabled");
    cy.get(".o_field_widget[name=mandatory] input").should("be.checked").and("be.disabled");
    cy.get(".o_field_widget[name=code]").should("contain", "test_result.rejected").find("input").should("not.exist");
    cy.then(() => snapshot(mandatory)).then((before) => {
      const refused = (method, args) => {
        callRefused("mail.message.subtype", method, args).should("eq", MESSAGE);
        snapshot(mandatory).should("deep.equal", before);
      };
      [false, 0, "", null, [], {}].forEach((value) => refused("write", [[mandatory.id], { enabled: value }]));
      refused("write", [[mandatory.id], { mandatory: false }]);
      refused("write", [[mandatory.id], { code: "test_result.rejected.changed" }]);
      refused("unlink", [[mandatory.id]]);
    });
  });

  it("TC-F25-03 lets the administrator turn an optional reminder off and back on through its form", () => {
    cy.then(() => cy.visit(`/odoo/notification-events/${optional.id}`));
    cy.get(".o_field_widget[name=enabled] input").should("be.enabled").check();
    cy.then(() => {
      if (!originalEnabled) {
        save();
      }
    });
    cy.get(".o_field_widget[name=enabled] input").uncheck();
    save();
    cy.reload();
    cy.get(".o_field_widget[name=enabled] input").should("not.be.checked");
    cy.then(() => callAs(ADMINISTRATOR, "mail.message.subtype", "read", [[optional.id], ["enabled"]]))
      .should(([event]) => expect(event.enabled).to.equal(false));
    cy.get(".o_field_widget[name=enabled] input").check();
    save();
    cy.reload();
    cy.get(".o_field_widget[name=enabled] input").should("be.checked");
    cy.then(() => callAs(ADMINISTRATOR, "mail.message.subtype", "read", [[optional.id], ["enabled"]]))
      .should(([event]) => expect(event.enabled).to.equal(true));
  });
});

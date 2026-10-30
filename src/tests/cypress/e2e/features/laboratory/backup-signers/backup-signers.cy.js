import { callAs, callRefused, refAs } from "../../../../support/odoo";
import { openTab, pick, save } from "../../../../support/form";
import { ADMINISTRATOR, BACKUP_PERSON, HEAD_ROLE, clearBackup, enteredResult, giveBackup, today } from "./setup";

// Today as the administrator's date field reads it, such as "10/30/2026".
function shownToday() {
  return new Date(`${today()}T00:00:00Z`).toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric", timeZone: "UTC" });
}

describe("Backup signers", () => {
  beforeEach(() => clearBackup());

  it("TC-F430-1 gives the head of department's role to a backup until today, who approves a sent result", () => {
    enteredResult({ sent: true }).then((result) => {
      cy.signInAs("administrator");
      cy.openRecord(BACKUP_PERSON);
      openTab("role_grants");
      cy.get(".o_field_widget[name=role_grant_ids] .o_field_x2many_list_row_add button").click();
      pick("role_id", "Head of department");
      cy.get(".o_field_widget[name=date_end] input").clear().type(shownToday());
      save();
      cy.contains(".o_field_widget[name=role_grant_ids] .o_data_row", "Head of department");
      refAs(ADMINISTRATOR, BACKUP_PERSON).then((person) =>
        refAs(ADMINISTRATOR, HEAD_ROLE).then((role) =>
          callAs(ADMINISTRATOR, "medilab.person", "read", [[person.id], ["role_ids"]]).then(([read]) =>
            expect(read.role_ids, "roles of the backup").to.include(role.id),
          ),
        ),
      );

      cy.signInAs("backup_signer");
      cy.openRecord(result);
      cy.signRecord();
      cy.contains(".o_statusbar_status .o_arrow_button_current", "Approved");
      cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
    });
  });

  it("TC-F430-2 lets a backup send a result at the tester's level in their own name, and then not approve it", () => {
    giveBackup();
    enteredResult().then((result) => {
      cy.signInAs("backup_signer");
      cy.openRecord(result);
      cy.signRecord();
      cy.contains(".o_statusbar_status .o_arrow_button_current", "Awaiting Approval");
      cy.get(".o_form_statusbar button[name=action_sign]").should("not.exist");
      cy.readRecord(result, ["status"]).its("status").should("eq", "requested");
      callRefused("medilab.test.result", "action_sign", [[result.id]]).should("contain", "You have already signed this document.");
    });
  });
});

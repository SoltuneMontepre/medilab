import { call, callAs, callRefused, refAs } from "../../../../support/odoo";
import { newRecord, pick } from "../../../../support/form";
import { ADMINISTRATOR, HEAD, receivedSample, releaseFixtures, resetFixtures } from "../../../flows/wf-03-testing-scheduling/setup";

// The deputy head of Chemistry is not authorized for any parameter.
const UNAUTHORIZED = "Phan Thi Thu";
const AUTHORIZED = "Dang Thi Lan";

const readTask = (task) =>
  callAs(ADMINISTRATOR, "medilab.task", "read", [[task.id], ["status", "assignee_id"]]).then(([read]) => read);

function openAssign(task) {
  cy.openRecord({ model: "medilab.task", id: task.id });
  cy.contains(".o_statusbar_buttons button", /^Assign$/).click();
  cy.get(".modal .o_field_widget[name=assignee_id]").should("be.visible");
}

beforeEach(resetFixtures);
afterEach(releaseFixtures);

describe("Parameter authorization", () => {
  it("TC-F421-01 offers the head only authorized people and refuses an unauthorized assignment", () => {
    receivedSample().then(({ tests: [lead] }) => {
      cy.signInAs("head_of_department");
      openAssign(lead.task);
      cy.get(".modal .o_field_widget[name=assignee_id] input").type("Thi");
      cy.get(".o-autocomplete--dropdown-menu").should("contain", AUTHORIZED).and("not.contain", UNAUTHORIZED);
      refAs(HEAD, "sol_demo.demo_person_backup_signer").then((person) => {
        const context = { active_ids: [lead.task.id] };
        call("medilab.task.reassign", "create", [{ assignee_id: person.id }], { context }).then((wizard) =>
          callRefused("medilab.task.reassign", "action_confirm", [[wizard]], { context }).should(
            "match",
            new RegExp(`^${UNAUTHORIZED} is not authorized to test `),
          ),
        );
      });
      readTask(lead.task).should((task) => {
        expect(task.status).to.equal("open");
        expect(task.assignee_id).to.equal(false);
      });
    });
  });

  it("TC-F421-02 assigns an authorized tester through the assign dialog", () => {
    receivedSample().then(({ tests: [lead] }) => {
      cy.signInAs("head_of_department");
      openAssign(lead.task);
      pick("assignee_id", AUTHORIZED);
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      readTask(lead.task).should((task) => {
        expect(task.status).to.equal("assigned");
        expect(task.assignee_id[1]).to.equal(AUTHORIZED);
      });
    });
  });

  it("TC-F421-03 lets the lab head authorize a person, and nobody else", () => {
    const name = `Arsenic (As) ${Date.now()}`;
    refAs(ADMINISTRATOR, "sol_demo.demo_parameter_group_heavy_metals").then((group) =>
      callAs(ADMINISTRATOR, "medilab.test.parameter", "create", [{ name, main_group_id: group.id, group_ids: [[6, 0, [group.id]]] }]),
    ).then((parameterId) => {
      cy.signInAs("head_of_department");
      refAs(HEAD, "sol_demo.demo_person_backup_signer").then((person) =>
        callRefused("medilab.parameter.authorization", "create", [{ person_id: person.id, parameter_id: parameterId }]).should(
          "contain",
          "Parameter Authorization",
        ),
      );

      cy.signInAs("lab_head");
      newRecord("/odoo/parameter-authorizations");
      pick("person_id", UNAUTHORIZED);
      pick("parameter_id", name);
      cy.get(".o_list_button_save").click();
      cy.get(".o_list_button_save").should("not.exist");
      call("medilab.parameter.authorization", "search_read", [[["parameter_id", "=", parameterId]]], { fields: ["person_id"] }).should(
        (rows) => expect(rows.map((row) => row.person_id[1])).to.deep.equal([UNAUTHORIZED]),
      );
    });
  });
});

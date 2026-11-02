import { pick } from "../../../support/form";
import { callAs, refAs } from "../../../support/odoo";

const HEAD = "demo.head_of_department";
const ADMINISTRATOR = "demo.administrator";
const TASK_FIELDS = [
  "name", "type_id", "status", "assignee_id", "assigned_by_id", "department_id", "reassign_reason",
  "deadline", "planned_start", "planned_end", "document_model", "document_id", "write_uid", "write_date",
];

function snapshot(task) {
  return callAs(ADMINISTRATOR, "medilab.task", "read", [[task.id], TASK_FIELDS]).then(([read]) =>
    callAs(ADMINISTRATOR, "calendar.event", "search_read", [[["medilab_task_id", "=", task.id]]], {
      fields: ["start", "stop", "user_id", "partner_ids", "write_date"], order: "id",
    }).then((events) => ({ task: read, events })),
  );
}

describe("Task reassignment reasons", () => {
  let task;

  beforeEach(() => {
    task = null;
    refAs(HEAD, "sol_laboratory.task_type_general").then((type) =>
      refAs(HEAD, "sol_demo.demo_hr_department_chemistry").then((department) =>
        refAs(HEAD, "sol_demo.demo_person_tester").then((assignee) => {
          const name = `Reassignment reason ${Date.now()}-${Cypress._.random(100000)}`;
          return callAs(HEAD, "medilab.task", "create", [{
            name, type_id: type.id, department_id: department.id, assignee_id: assignee.id,
            status: "assigned", deadline: new Date(Date.now() + 86400000).toISOString().slice(0, 19).replace("T", " "),
          }]).then((id) => { task = { model: "medilab.task", id, name }; });
        }),
      ),
    );
  });

  afterEach(() => {
    if (task) {
      callAs(HEAD, "medilab.task", "read", [[task.id], ["status"]]).then(([read]) => {
        if (!["done", "cancelled"].includes(read.status)) {
          callAs(HEAD, "medilab.task", "action_cancel", [[task.id]]);
        }
      });
    }
  });

  it("TC-F23-03 refuses a whitespace reason and accepts a corrected reason in the same assignment dialog", () => {
    cy.signInAs("head_of_department");
    cy.then(() => cy.openRecord(task));
    cy.contains(".o_statusbar_buttons button", /^Assign$/).click();
    cy.get(".modal .o_field_widget[name=assignee_id]").should("be.visible");
    pick("assignee_id", "Ly Van Hung");
    cy.get(".modal .o_field_widget[name=reason] textarea").type("   ");
    cy.get(".modal:visible").then(($dialog) => {
      const dialog = $dialog[0];
      cy.expectRefusal({
        read: () => snapshot(task),
        action: () => cy.get(".modal button[name=action_confirm]").click(),
        message: `Give a reason for moving ${task.name} to another person or department.`,
      });
      cy.get(".o_error_dialog button.btn-primary").click();
      cy.get(".o_error_dialog").should("not.exist");
      cy.get(".modal:visible").should(($current) => expect($current[0]).to.equal(dialog));
      cy.get(".modal .o_field_widget[name=reason] textarea").clear().type("Ly Van Hung will finish this task.");
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      snapshot(task).should(({ task: saved, events }) => {
        expect(saved.assignee_id[1]).to.equal("Ly Van Hung");
        expect(saved.reassign_reason).to.equal("Ly Van Hung will finish this task.");
        expect(saved.status).to.equal("assigned");
        expect(saved.department_id[1]).to.equal("Chemistry");
        expect(events).to.be.empty;
      });
    });
  });
});

import { addLine, discardRefused, pick, search } from "../../../support/form";
import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { staffRequest } from "../wf-02-sample-reception/setup";
import { approvedResult, assignedTest } from "../wf-04-result-approval/setup";
import { releaseFixtures } from "../wf-03-testing-scheduling/setup";

const ACTIONS = ".o_form_view .o_statusbar_buttons";

// Only the bookings these tests made are released, so the machines stay free for the next ones.
afterEach(releaseFixtures);

describe("SF-08 people, roles and approval chains (F-19, F-33)", () => {
  describe("with a permission given to a person", () => {
    const login = "demo.microbiology_tester";

    // Gives the Microbiology tester's person the right to read every test request (4), or takes it back (3).
    function setOwnPermission(command) {
      return refAs("demo.administrator", "sol_demo.demo_person_microbiology_tester").then((person) =>
        refAs("demo.administrator", "sol_laboratory.permission_test_request_read_all").then((permission) =>
          callAs("demo.administrator", "medilab.person", "write", [[person.id], { permission_ids: [[command, permission.id]] }]),
        ),
      );
    }

    // Taken back even when the test fails, so the person never keeps a wider access in later tests.
    afterEach(() => setOwnPermission(3));

    it("TC-F19-01 gives a person every permission of their roles plus their own", () => {
      staffRequest().then((request) => {
        setOwnPermission(3);
        cy.signInAs("microbiology_tester");
        callRefused("medilab.test.request", "search", [[]]).should("contain", "medilab.test.request");
        setOwnPermission(4);
        // Testers' own role still applies alongside the permission given to the person.
        callAs(login, "medilab.test.request", "search_count", [[["id", "=", request.id]]]).should("eq", 1);
        callAs(login, "medilab.sample", "search_count", [[["id", "=", request.samples[0].id]]]).should("eq", 1);
      });
    });
  });

  it("TC-F19-02 hides another department's records and keeps a person's team in their department", () => {
    cy.signInAs("head_of_department");
    cy.visit("/odoo/department-queue");
    cy.get(".o_list_renderer").should("not.contain", "Microbiology");
    callAs("demo.administrator", "medilab.task", "search_count", [[["department_id.name", "=", "Microbiology"]]]).should("be.greaterThan", 0);
    callAs("demo.head_of_department", "medilab.task", "search_count", [[["department_id.name", "=", "Microbiology"]]]).should("eq", 0);
    refAs("demo.administrator", "sol_demo.demo_person_chemistry_tester").then((person) =>
      refAs("demo.administrator", "sol_demo.demo_hr_department_pathogens").then((pathogens) => {
        cy.signInAs("administrator");
        callRefused("medilab.person", "write", [[person.id], { team_id: pathogens.id }]).should(
          "match",
          /^Pathogens is not a team of the department of /,
        );
      }),
    );
  });

  it("TC-F19-03 shows a person without a permission no menu or button, and refuses the call", () => {
    staffRequest({ confirm: false }).then((request) => {
      // Testers keep the change requests of the Requests menu, but not its test requests.
      cy.signInAs("tester");
      cy.visit("/odoo/change-requests");
      cy.contains(".o_menu_sections .dropdown-toggle", "Requests").click();
      cy.get(".o-dropdown--menu").should("contain", "Change Requests").and("not.contain", "Test Requests");
      callRefused("medilab.test.request", "action_confirm", [[request.id]]).should("contain", "medilab.test.request");
    });
  });

  it("TC-F33-02 lets no signer withdraw once the process completes", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      approvedResult(test, { value: 0.004 }).then((result) => {
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.get(`${ACTIONS} button[name=action_withdraw]`).should("not.exist");
        callRefused("medilab.test.result", "action_withdraw", [[result.id]]).should(
          "eq",
          "The process of the document is completed, so a signature cannot be withdrawn.",
        );
        cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
      });
    });
  });

  it("TC-F33-03 refuses a second chain for a document type's purpose, and two levels of a chain in one position", () => {
    cy.signInAs("administrator");
    callRefused("medilab.approval.chain", "create", [{ name: "Ký kết quả", document_model: "medilab.test.result", purpose: "signing" }]).should(
      "contain",
      "A document type cannot have two chains for the same purpose.",
    );
    cy.openRecord("sol_demo.demo_approval_chain_test_result_signing").then((chain) => {
      cy.expectRefusal({
        read: () => call("medilab.approval.level", "search_read", [[["chain_id", "=", chain.id]]], { fields: ["sequence", "write_date"] }),
        action: () => {
          addLine("level_ids");
          cy.get(".o_selected_row [name=sequence] input").clear().type("10");
          cy.get(".o_selected_row [name=name] input").type("Lab head");
          pick("role_id", "Lab head");
          cy.get(".o_form_button_save").click();
        },
        message: "A chain cannot have two levels in the same position.",
      });
      discardRefused();
    });
  });
});

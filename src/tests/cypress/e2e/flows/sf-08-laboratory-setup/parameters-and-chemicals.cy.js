import { addLine, discard, discardRefused, newRecord, openTab, pick, saveAndWait, search } from "../../../support/form";
import { call, callRefused, resolveRecord } from "../../../support/odoo";
import { newParameter } from "../wf-04-result-approval/setup";

// Adds an in-house way of testing in Chemistry to the parameter form.
function addWay(method) {
  addLine("method_ids");
  pick("method_id", method);
  pick("department_id", "Chemistry");
  cy.get(".o_selected_row .o_field_widget[name=department_id] input").should("have.value", "Chemistry");
}

// Selects the record named `name` in the list its menu opens, and opens the list's Actions menu.
function listActions(path, name) {
  cy.visit(`/odoo/${path}`);
  cy.get(".o_data_row").should("exist");
  search(name);
  cy.contains(".o_data_row", name).find(".o_list_record_selector input").check();
  cy.contains(".o_control_panel button", "Actions").click();
}

describe("SF-08 test parameters and chemicals (F-29, F-31)", () => {
  it("TC-F29-01 saves a parameter with several ways of testing and groups", () => {
    const name = `Arsenic (As) ${Date.now()}`;
    cy.signInAs("administrator");
    newRecord("/odoo/test-parameters");
    cy.get(".o_field_widget[name=name] input").type(name);
    pick("group_ids", "Heavy metals");
    pick("group_ids", "Physicochemical");
    pick("main_group_id", "Heavy metals");
    addWay("TCVN 7602:2007");
    addWay("ISO 17294-2:2016");
    saveAndWait("medilab.test.parameter");
    cy.reload();
    cy.get(".o_field_widget[name=group_ids] .o_tag").should("have.length", 2);
    cy.get(".o_field_widget[name=method_ids] .o_data_row").should("have.length", 2);
    call("medilab.test.parameter", "search_read", [[["name", "=", name]]], { fields: ["main_group_id", "group_ids", "method_ids"] }).should(
      ([parameter]) => {
        expect(parameter.main_group_id[1]).to.equal("Heavy metals");
        expect(parameter.group_ids).to.have.length(2);
        expect(parameter.method_ids).to.have.length(2);
      },
    );
  });

  it("TC-F29-02 refuses a main group that is not one of the parameter's groups, and an in-house way without a department", () => {
    newParameter().then((parameter) => {
      cy.signInAs("administrator");
      cy.openRecord(parameter);
      cy.expectRefusal({
        read: () => cy.readRecord(parameter, ["group_ids", "main_group_id", "write_date"]),
        action: () => {
          pick("group_ids", "Physicochemical");
          cy.contains(".o_field_widget[name=group_ids] .o_tag", "Heavy metals").find(".o_delete").click();
          cy.get(".o_form_button_save").click();
        },
        message: `The main group of ${parameter.name} must be one of its groups.`,
      });
      discardRefused();
      addLine("method_ids");
      pick("method_id", "ISO 17294-2:2016");
      cy.get(".o_form_button_save").click();
      cy.get(".o_selected_row td[name=department_id]").should("have.class", "o_invalid_cell");
      cy.get(".o_form_button_save").should("be.visible");
      call("medilab.parameter.method", "search_count", [[["parameter_id", "=", parameter.id]]]).should("eq", 1);
      discard();
    });
  });

  it("TC-F29-03 refuses a second active way with the same method, and archives a parameter instead of deleting it", () => {
    newParameter().then((parameter) => {
      cy.signInAs("administrator");
      cy.openRecord(parameter);
      cy.expectRefusal({
        read: () => call("medilab.parameter.method", "search_read", [[["parameter_id", "=", parameter.id]]], { fields: ["method_id", "write_date"] }),
        action: () => {
          addWay("TCVN 7602:2007");
          cy.get(".o_form_button_save").click();
        },
        message: "The parameter is already tested with this method by the same laboratory.",
      });
      discardRefused();
      // No active way of testing may use the parameter when it is archived.
      call("medilab.parameter.method", "search", [[["parameter_id", "=", parameter.id]]]).then((ways) =>
        call("medilab.parameter.method", "action_archive", [ways]),
      );
      listActions("test-parameters", parameter.name);
      cy.get(".o-dropdown--menu .o-dropdown-item").should("not.contain", "Delete");
      cy.contains(".o-dropdown--menu .o-dropdown-item", "Archive").click();
      cy.get(".modal-footer .btn-primary").click();
      cy.contains(".o_data_row", parameter.name).should("not.exist");
      callRefused("medilab.test.parameter", "unlink", [[parameter.id]]).should("match", /^You are not allowed to delete 'Test Parameter'/);
      cy.readRecord(parameter, ["active"]).its("active").should("eq", false);
    });
  });

  it("TC-F31-01 shows the chemicals a method uses, and the methods that use a chemical", () => {
    cy.signInAs("administrator");
    cy.openRecord("sol_demo.demo_testing_method_tcvn_7602");
    openTab("chemicals");
    cy.get(".o_field_widget[name=chemical_ids] .o_data_row").should("contain", "HC-001").and("contain", "Nitric acid 65%");
    cy.openRecord("sol_demo.demo_chemical_nitric_acid");
    cy.get(".o_field_widget[name=method_ids] .o_data_row").should("contain", "TCVN 7602:2007").and("contain", "ISO 17294-2:2016");
  });

  it("TC-F31-02 records a chemical's CAS number, formula, grade and storage conditions", () => {
    const code = `HC-${Date.now()}`;
    cy.signInAs("administrator");
    newRecord("/odoo/chemicals");
    cy.get(".o_field_widget[name=name] input").type("Hydrochloric acid 37%");
    cy.get(".o_field_widget[name=code] input").type(code);
    cy.get(".o_field_widget[name=cas_number] input").type("7647-01-0");
    cy.get(".o_field_widget[name=formula] input").type("HCl");
    cy.get(".o_field_widget[name=grade] input").type("AR, 37 %");
    cy.get(".o_field_widget[name=storage_conditions] textarea").type("Tủ axit, tránh xa chất oxy hóa.");
    saveAndWait("medilab.chemical");
    call("medilab.chemical", "search_read", [[["code", "=", code]]], {
      fields: ["cas_number", "formula", "grade", "storage_conditions"],
    }).should(([chemical]) => {
      expect(chemical.cas_number).to.equal("7647-01-0");
      expect(chemical.formula).to.equal("HCl");
      expect(chemical.grade).to.equal("AR, 37 %");
      expect(chemical.storage_conditions).to.equal("Tủ axit, tránh xa chất oxy hóa.");
    });
  });

  it("TC-F31-03 refuses to delete a chemical that a method uses", () => {
    cy.signInAs("administrator");
    resolveRecord("sol_demo.demo_chemical_nitric_acid").then((chemical) => {
      cy.expectRefusal({
        read: () => cy.readRecord(chemical, ["method_ids", "write_date"]),
        action: () => {
          listActions("chemicals", "Nitric acid 65%");
          cy.contains(".o-dropdown--menu .o-dropdown-item", "Delete").click();
          cy.get(".modal-footer .btn-danger").click();
        },
        message: "This cannot be deleted while these records refer to it:",
      });
    });
  });
});

import { newRecord, openTab, pick, save, search } from "../../../support/form";
import { call, callAs, callRefused, resolveRecord } from "../../../support/odoo";
import { orderAt } from "../wf-01-order-to-test-request/setup";
import {
  HEAD,
  LAB_HEAD,
  PARAMETERS,
  approvedResult,
  bookAndStart,
  enterResult,
  newParameter,
  newRegulation,
  rejectedResult,
  sampleInTesting,
  sentResult,
  testOf,
} from "./setup";

const REJECTION = "Hàm lượng chì cao bất thường so với mẫu cùng lô; đề nghị đo lại.";
const CANCELLATION = "Mẫu không đủ thể tích để phân tích chì.";

// The results of a sample test, the latest attempt first, as the signed-in user reads them.
function resultsOf(test) {
  return call("medilab.test.result", "search_read", [[["sample_test_id", "=", test.id]]], {
    fields: ["attempt", "status", "is_reported", "value_display"],
    order: "attempt desc",
  }).then((results) => results.map((result) => ({ ...result, model: "medilab.test.result" })));
}

// Opens the result form of a new result from the sample test's form.
function enterResultOnScreen(test) {
  cy.openRecord(test);
  cy.get(".o_statusbar_buttons button[name=action_enter_result]:visible").click();
  cy.get(".o_form_view .o_field_widget[name=sample_test_id]").should("be.visible");
}

function concludeOnScreen(conclusion) {
  cy.get(`.o_field_widget[name=conclusion] input[data-value=${conclusion}]`).check();
}

// Adds a line to an editable list field of the form.
function addLine(field) {
  cy.get(`.o_field_widget[name=${field}] .o_field_x2many_list_row_add button`).click();
}

// Adds an in-house way of testing in Chemistry to the parameter form.
function addWay(method, unit) {
  addLine("method_ids");
  pick("method_id", method);
  pick("unit_id", unit);
  pick("department_id", "Chemistry");
  cy.get(".o_selected_row .o_field_widget[name=department_id] input").should("have.value", "Chemistry");
}

// Selects the record named `name` in the list its menu opens, and opens the list's Actions menu.
function listActions(path, name) {
  cy.visit(`/odoo/${path}`);
  cy.get(".o_data_row").should("exist");
  search(name);
  cy.contains(".o_data_row", name).find(".o_list_record_selector input").check();
  cy.contains(".o_control_panel button.dropdown-toggle", "Actions").click();
}

// Discards the form's unsaved changes, so leaving the page does not save them, and waits until the form has read the
// record again, which would otherwise drop a line added meanwhile.
function discard() {
  cy.intercept("POST", "/web/dataset/call_kw/*/web_read").as("reread");
  cy.get(".o_form_button_cancel").click();
  cy.wait("@reread");
  cy.get(".o_form_button_save").should("not.be.visible");
}

// Closes the dialog that shows a refusal, then discards the changes it refused.
function discardRefused() {
  cy.get(".o_error_dialog .btn-close").click();
  cy.get(".o_error_dialog").should("not.exist");
  discard();
}

// Archives the parameter's one way of testing with its Active toggle, so no active way uses the parameter. The row is
// edited first: a click on the toggle of a row not in edition can be taken by opening the row.
function archiveWay() {
  cy.get(".o_field_widget[name=method_ids] .o_data_row td[name=lod]").click();
  cy.get(".o_field_widget[name=method_ids] .o_selected_row td[name=active] input").click();
  cy.get(".o_field_widget[name=method_ids] .o_data_row td[name=active] input").should("not.be.checked");
  save();
}

describe("WF-04 Result entry and approval", () => {
  it("TC-WF04-M lets the tester follow the steps and send a number with its conclusion, which the head approves", () => {
    sampleInTesting().then((sample) => {
      const [test] = sample.tests;
      cy.signInAs("tester");
      cy.openRecord(test.task);
      openTab("method_steps");
      cy.readRecord(test.task, ["method_step_ids"])
        .then(({ method_step_ids }) =>
          call("medilab.testing.method.step", "read", [method_step_ids, ["sequence", "duration_minutes", "instruction", "note"]]),
        )
        .then((steps) => {
          expect(steps, "steps of the method").not.to.be.empty;
          const ordered = Cypress._.sortBy(steps, "sequence");
          cy.get(".o_field_widget[name=method_step_ids] .o_data_row")
            .should("have.length", ordered.length)
            .each((row, index) => {
              const step = ordered[index];
              cy.wrap(row).find("td[name=sequence]").should("have.text", String(step.sequence));
              cy.wrap(row).find("td[name=duration_minutes]").should("have.text", String(step.duration_minutes));
              cy.wrap(row).find("td[name=instruction]").should("have.text", step.instruction);
              cy.wrap(row)
                .find("td[name=note]")
                .should("have.text", step.note || "");
            });
        });
      cy.get(".o_form_view button[name=action_open_document]").click();
      cy.get(".o_statusbar_buttons button[name=action_enter_result]:visible").click();
      cy.readRecord(test.booking, ["machine_id"]).then(({ machine_id: [, machine] }) =>
        cy.get(".o_field_widget[name=machine_id] input").should("have.value", machine),
      );
      cy.get(".o_field_widget[name=started_at] button").invoke("text").should("not.be.empty");
      cy.get(".o_field_widget[name=limit_max]").should("contain", "0.01");
      cy.get(".o_field_widget[name=limit_unit_id]").should("contain", "mg/L");
      cy.get(".o_field_widget[name=value] input").clear().type("0.004");
      concludeOnScreen("pass");
      save();
      cy.sendRecord("action_sign");
      cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").should("exist");
      resultsOf(test).then(([result]) => {
        expect(result.status).to.equal("requested");
        callRefused("medilab.test.result", "write", [[result.id], { value: 0.003 }]).should(
          "eq",
          "The document has signatures; withdraw them before changing it.",
        );
        cy.signInAs("head_of_department");
        cy.openRecord(result);
        cy.signRecord();
        cy.get(".o_statusbar_buttons button[name=action_sign]").should("not.exist");
        cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
      });
      cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
      cy.readRecord(test.task, ["status"]).its("status").should("eq", "done");
      cy.readRecord(sample, ["status"]).its("status").should("eq", "completed");
    });
  });

  it("TC-WF04-A1 lets the tester enter and send a text result", () => {
    sampleInTesting([PARAMETERS.lead], { regulation: false }).then(({ tests: [test] }) => {
      cy.signInAs("tester");
      enterResultOnScreen(test);
      cy.get(".o_field_widget[name=conclusion]").should("not.exist");
      cy.get(".o_field_widget[name=value_text] input").type("Not detected").blur();
      cy.get(".o_field_widget[name=value]").should("not.exist");
      save();
      cy.sendRecord("action_sign");
      cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").should("exist");
      resultsOf(test).should(([result]) => {
        expect(result.status).to.equal("requested");
        expect(result.value_display).to.equal("Not detected");
      });
    });
  });

  it("TC-WF04-A2 keeps a rejected result on record when the tester retests and the head approves the new one", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      sentResult(test, { value: 0.02, conclusion: "fail" }).then((rejected) => {
        cy.signInAs("head_of_department");
        cy.openRecord(rejected);
        cy.rejectRecord(REJECTION);
        cy.readRecord(rejected, ["status"]).its("status").should("eq", "rejected");
        cy.readRecord(test, ["status"]).its("status").should("eq", "testing");

        cy.signInAs("tester");
        call(
          "mail.message",
          "search_read",
          [
            [
              ["model", "=", "medilab.test.result"],
              ["res_id", "=", rejected.id],
              ["needaction", "=", true],
            ],
          ],
          { fields: ["body"] },
        ).should(([message]) => expect(message.body).to.contain(REJECTION));
        enterResultOnScreen(test);
        cy.get(".o_field_widget[name=value] input").clear().type("0.005");
        concludeOnScreen("pass");
        save();
        cy.sendRecord("action_sign");
        cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").should("exist");
        resultsOf(test).then(([retest]) => {
          cy.signInAs("head_of_department");
          cy.openRecord(retest);
          cy.signRecord();
          cy.get(".o_statusbar_buttons button[name=action_sign]").should("not.exist");
        });
        resultsOf(test).should((results) => {
          expect(results.map(({ attempt, status, is_reported }) => [attempt, status, is_reported])).to.deep.equal([
            [2, "approved", true],
            [1, "rejected", false],
          ]);
        });
        cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
      });
    });
  });

  it("TC-WF04-A3 lets the tester withdraw a result they sent before the head acts", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      sentResult(test, { value: 0.004, conclusion: "pass" }).then((result) => {
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").click();
        cy.get(".o_statusbar_buttons button[name=action_sign]:visible").should("exist");
        cy.get(".o_field_widget[name=value] input").should("be.enabled");
        cy.readRecord(result, ["status"]).its("status").should("eq", "none");
        cy.readRecord(test, ["status"]).its("status").should("eq", "testing");
      });
    });
  });

  it("TC-WF04-A5 lets the head cancel a test that cannot be done, and completes the sample and its report without it", () => {
    sampleInTesting([PARAMETERS.lead, PARAMETERS.ph]).then((sample) => {
      testOf(sample, PARAMETERS.ph).then((ph) => approvedResult(ph, { value: 7.2, conclusion: "pass" }).as("phResult"));
      testOf(sample, PARAMETERS.lead).then((lead) => {
        rejectedResult(lead, { value: 0.02, conclusion: "fail" }, REJECTION);
        bookAndStart(lead);
        cy.signInAs("head_of_department");
        cy.openRecord(lead);
        cy.rejectRecord(CANCELLATION, { action: "action_cancel" });
        cy.get(".o_field_widget[name=cancel_reason]").should("contain", CANCELLATION);
        cy.readRecord(lead, ["status", "cancel_reason"]).should((read) => {
          expect(read.status).to.equal("cancelled");
          expect(read.cancel_reason).to.equal(CANCELLATION);
        });
        cy.readRecord(lead.task, ["status"]).its("status").should("eq", "cancelled");
        cy.then(() => cy.readRecord(lead.booking, ["status"]))
          .its("status")
          .should("eq", "cancelled");
      });
      cy.readRecord(sample, ["status"]).its("status").should("eq", "completed");
      cy.get("@phResult").then((phResult) =>
        callAs(LAB_HEAD, "medilab.test.report", "search_read", [[["request_id", "=", sample.requestId]]], {
          fields: ["result_ids"],
        }).should(([report]) => expect(report.result_ids).to.deep.equal([phResult.id])),
      );
    });
  });

  it("TC-WF04-E1 does not let the person who entered a result approve it", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      sentResult(test, { value: 0.004, conclusion: "pass" }, { enteredBy: HEAD }).then((result) => {
        cy.signInAs("head_of_department");
        cy.openRecord(result);
        cy.get(".o_statusbar_buttons button[name=action_sign]").should("not.exist");
        callRefused("medilab.test.result", "action_sign", [[result.id]]).should("eq", "You entered this result, so another person must approve it.");
        cy.readRecord(result, ["status"]).its("status").should("eq", "requested");
      });
    });
  });

  it("TC-WF04-E2 refuses to send a result on a sample with a regulation without a conclusion", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      enterResult(test, { value: 0.004 }).then((result) => {
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.expectRefusal({
          read: () => cy.readRecord(result, ["status", "value", "conclusion", "write_date"]),
          action: () => cy.sendRecord("action_sign"),
          message: "Set the conclusion against the regulation before sending the result.",
        });
      });
    });
  });

  it("TC-WF04-E3 refuses to cancel a test without a reason, or a test with an approved result", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.expectRefusal({
        read: () => cy.readRecord(test, ["status", "cancel_reason", "write_date"]),
        action: () => {
          cy.get(".o_statusbar_buttons button.btn-danger:visible").click();
          cy.get(".modal:visible [name=reason] textarea").type("   ");
          cy.get(".modal:visible button[name=action_cancel]").click();
        },
        message: "Give a reason for cancelling the test.",
      });
    });
    sampleInTesting().then(({ tests: [test] }) => {
      approvedResult(test, { value: 0.004, conclusion: "pass" });
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.get(".o_statusbar_buttons button.btn-danger").should("not.exist");
      callRefused("medilab.sample.test", "action_cancel", [[test.id], CANCELLATION]).should(
        "match",
        /^Only a waiting, assigned or testing sample test can be cancelled: /,
      );
      cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
    });
  });
});

describe("WF-04 feature acceptance criteria", () => {
  it("TC-F29-01 saves a parameter with several ways of testing, groups and sample types", () => {
    const name = `Arsenic (As) ${Date.now()}`;
    cy.signInAs("administrator");
    newRecord("/odoo/test-parameters");
    cy.get(".o_field_widget[name=name] input").type(name);
    pick("group_ids", "Heavy metals");
    pick("group_ids", "Physicochemical");
    pick("main_group_id", "Heavy metals");
    pick("sample_type_ids", "Bottled water");
    pick("sample_type_ids", "Surface water");
    addWay("TCVN 7602:2007", "mg/kg");
    addWay("ISO 17294-2:2016", "µg/L");
    save();
    cy.reload();
    cy.get(".o_field_widget[name=group_ids] .o_tag").should("have.length", 2);
    cy.get(".o_field_widget[name=sample_type_ids] .o_tag").should("have.length", 2);
    cy.get(".o_field_widget[name=method_ids] .o_data_row").should("have.length", 2);
    call("medilab.test.parameter", "search_read", [[["name", "=", name]]], {
      fields: ["main_group_id", "group_ids", "sample_type_ids", "method_ids"],
    }).should(([parameter]) => {
      expect(parameter.main_group_id[1]).to.equal("Heavy metals");
      expect(parameter.group_ids).to.have.length(2);
      expect(parameter.sample_type_ids).to.have.length(2);
      expect(parameter.method_ids).to.have.length(2);
    });
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
      pick("unit_id", "µg/L");
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
          addWay("TCVN 7602:2007", "mg/kg");
          cy.get(".o_form_button_save").click();
        },
        message: "The parameter is already tested with this method by the same laboratory.",
      });
      discardRefused();
      archiveWay();
      call("medilab.parameter.method", "search_count", [[["parameter_id", "=", parameter.id]]]).should("eq", 0);
      listActions("test-parameters", parameter.name);
      cy.get(".o-dropdown--menu .o-dropdown-item").should("not.contain", "Delete");
      cy.contains(".o-dropdown--menu .o-dropdown-item", "Archive").click();
      cy.get(".modal footer .btn-primary").click();
      cy.contains(".o_data_row", parameter.name).should("not.exist");
      callRefused("medilab.test.parameter", "unlink", [[parameter.id]]).should("match", /^You are not allowed to delete 'Test Parameter'/);
      cy.readRecord(parameter, ["active"]).its("active").should("eq", false);
    });
  });

  it("TC-F30-02 refuses two steps of one method with the same number", () => {
    cy.signInAs("administrator");
    resolveRecord("sol_demo.demo_testing_method_tcvn_7602").then((method) => {
      cy.openRecord(method);
      cy.expectRefusal({
        read: () => call("medilab.testing.method.step", "search_read", [[["method_id", "=", method.id]]], { fields: ["sequence", "write_date"] }),
        action: () => {
          addLine("step_ids");
          cy.get(".o_selected_row [name=sequence] input").clear().type("1");
          cy.get(".o_selected_row [name=duration_minutes] input").clear().type("10");
          cy.get(".o_selected_row [name=instruction] textarea").type("Tráng chén nung bằng axit nitric.");
          cy.get(".o_form_button_save").click();
        },
        message: "Two steps of a testing method cannot have the same number.",
      });
      discardRefused();
    });
  });

  it("TC-F30-03 does not let a tester change a step", () => {
    cy.signInAs("tester");
    resolveRecord("sol_demo.demo_testing_method_tcvn_7602").then((method) => {
      cy.openRecord(method);
      cy.get(".o_field_widget[name=step_ids] .o_data_row").should("have.length.greaterThan", 0);
      cy.get(".o_field_widget[name=step_ids] .o_field_x2many_list_row_add").should("not.exist");
    });
    resolveRecord("sol_demo.demo_testing_method_step_tcvn_7602_1").then((step) => {
      callRefused("medilab.testing.method.step", "write", [[step.id], { duration_minutes: 20 }]).should(
        "match",
        /^You are not allowed to Edit these records: /,
      );
      cy.readRecord(step, ["duration_minutes"]).its("duration_minutes").should("eq", 15);
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
    save();
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
          cy.get(".modal footer .btn-danger").click();
        },
        message: "This cannot be deleted while these records refer to it:",
      });
    });
  });

  it("TC-F32-02 keeps a result's copied limit when the regulation changes, and holds one limit per parameter", () => {
    newRegulation(0.05).then((regulation) => {
      sampleInTesting([PARAMETERS.lead], { regulation }).then(({ tests: [test] }) => {
        enterResult(test, { value: 0.004 }).then((result) => {
          cy.signInAs("administrator");
          cy.openRecord(regulation);
          cy.get(".o_field_widget[name=limit_ids] .o_data_row td[name=max_value]").click();
          cy.get(".o_selected_row [name=max_value] input").clear().type("0.02");
          save();
          cy.readRecord(regulation, ["limit_ids"]).then(({ limit_ids: [limit] }) =>
            cy.readRecord({ model: "medilab.regulation.limit", id: limit }, ["max_value"]).its("max_value").should("eq", 0.02),
          );
          cy.readRecord(result, ["limit_max"]).its("limit_max").should("eq", 0.05);
          cy.expectRefusal({
            read: () => cy.readRecord(regulation, ["limit_ids", "write_date"]),
            action: () => {
              addLine("limit_ids");
              pick("parameter_id", "Lead (Pb)");
              cy.get(".o_selected_row [name=limit_text] input").type("Không phát hiện");
              cy.get(".o_form_button_save").click();
            },
            message: "A regulation sets at most one limit per parameter.",
          });
          discardRefused();
        });
      });
    });
  });

  it("TC-F33-02 lets no signer withdraw once the process completes or while a higher level's signature stands", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      approvedResult(test, { value: 0.004, conclusion: "pass" }).then((result) => {
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.get(".o_statusbar_buttons button[name=action_withdraw]").should("not.exist");
        callRefused("medilab.test.result", "action_withdraw", [[result.id]]).should(
          "eq",
          "The process of the document is completed, so a signature cannot be withdrawn.",
        );
        cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
      });
    });
    orderAt("approved", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_withdraw]").should("not.exist");
      callRefused("sale.order", "action_withdraw", [[order.id]]).should("eq", "Hãy rút lại chữ ký của các cấp cao hơn trước.");
      cy.readRecord(order, ["approval_status"]).its("approval_status").should("eq", "approved");
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

  it("TC-F34-02 sends only the latest result of a test for approval", () => {
    sampleInTesting().then(({ tests: [test] }) => {
      enterResult(test, { value: 0.004, conclusion: "pass" }).then((first) => {
        enterResult(test, { value: 0.005, conclusion: "pass" });
        cy.signInAs("tester");
        cy.openRecord(first);
        cy.get(".o_statusbar_buttons button[name=action_sign]").should("not.exist");
        callRefused("medilab.test.result", "action_sign", [[first.id]]).should(
          "eq",
          "Only the reported result of a sample test is sent for approval.",
        );
        cy.readRecord(first, ["status", "is_reported"]).should((read) => {
          expect(read.status).to.equal("none");
          expect(read.is_reported).to.equal(false);
        });
      });
    });
  });
});

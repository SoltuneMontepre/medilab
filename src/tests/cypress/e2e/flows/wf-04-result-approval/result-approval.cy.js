import { newRecord, openTab, pick, save, search } from "../../../support/form";
import { call, callAs, callRefused, refAs, resolveRecord } from "../../../support/odoo";
import { releaseFixtures } from "../wf-03-testing-scheduling/setup";
import {
  LAB_HEAD,
  TESTER,
  approvedResult,
  assignedTest,
  bookedLead,
  enteredResult,
  leadInTesting,
  newParameter,
  newRegulation,
  results,
  sentResult,
  testingTasks,
} from "./setup";

const ACTIONS = ".o_form_view .o_statusbar_buttons";
const CANCELLATION = "Mẫu không đủ thể tích để phân tích chì.";
// Lead in bottled water compared with QCVN 6-1:2010/BYT, which limits it there.
const COMPARED_WATER = { regulation: "sol_demo.demo_regulation_qcvn_6_1" };
// Lead in lettuce compared with QCVN 8-2:2011/BYT, which limits lead on cabbage but not on lettuce.
const LETTUCE_WITHOUT_LIMIT = {
  sampleType: "sol_demo.demo_sample_type_lettuce",
  state: "solid",
  regulation: "sol_demo.demo_regulation_qcvn_8_2",
};

// Chooses an assessment of the open result and saves it.
function assess(label) {
  cy.get(".o_field_widget[name=conclusion]").contains("label", label).click();
  save();
}

// Enters a value for the sample test through its form and saves the result.
function enterResult(test, value) {
  cy.openRecord(test);
  cy.signRecord("action_enter_result");
  cy.get(".o_field_widget[name=value] input").clear().type(value);
  save();
}

// Saves the form and waits for the server's answer, so what follows reads or changes the saved record.
function saveAndWait(model) {
  cy.intercept("POST", `/web/dataset/call_kw/${model}/web_save`).as("saved");
  save();
  cy.wait("@saved");
}

// Adds a line to an editable list field of the form and waits until it is edited.
function addLine(field) {
  cy.get(`.o_field_widget[name=${field}] .o_field_x2many_list_row_add button`).click();
  cy.get(`.o_field_widget[name=${field}] .o_selected_row`).should("exist");
}

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

// Only the bookings these tests made are released, so the machines stay free for the next ones.
afterEach(releaseFixtures);

describe("WF-04 Result entry and approval", () => {
  it("TC-WF04-M lets the tester enter and send a result, which completes their testing task, and the head approve it", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      cy.signInAs("tester");
      enterResult(test, "0.008");
      cy.get(".o_field_widget[name=conclusion]").should("not.exist");
      cy.signRecord();
      cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
      testingTasks(test).then((tasks) => expect(tasks.map((task) => task.status)).to.deep.equal(["done"]));
      cy.readRecord(test, ["status"]).its("status").should("eq", "result_entered");

      results(test).then(([result]) => {
        callRefused("medilab.test.result", "write", [[result.id], { value: 0.003 }]).should(
          "eq",
          "The document has signatures; withdraw them before changing it.",
        );
        cy.signInAs("head_of_department");
        cy.openRecord(result);
        cy.signRecord();
        cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
        cy.readRecord(result, ["status"]).its("status").should("eq", "approved");
        cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
      });
    });
  });

  it("TC-WF04-A2 lets the tester withdraw a sent result, which gives them back their testing task", () => {
    sentResult().then(({ test, result }) => {
      cy.signInAs("tester");
      cy.openRecord(result);
      cy.signRecord("action_withdraw");
      cy.get(`${ACTIONS} button[name=action_withdraw]`).should("not.exist");
      cy.readRecord(result, ["status"]).its("status").should("eq", "none");
      refAs(TESTER, "sol_demo.demo_person_tester").then((tester) =>
        testingTasks(test).then(([task, ...others]) => {
          expect(others).to.be.empty;
          expect(task.status).to.equal("assigned");
          expect(task.assignee_id[0]).to.equal(tester.id);
        }),
      );
    });
  });

  it("TC-WF04-E1 lets the head reject a result, which stays on record and opens a new testing task", () => {
    const reason = "Mẫu chuẩn kiểm tra đọc cao 15%, hiệu chuẩn lại máy AAS và đo lại.";
    sentResult().then(({ test, result }) => {
      cy.signInAs("head_of_department");
      cy.openRecord(result);
      cy.rejectRecord(reason);
      cy.readRecord(result, ["status"]).its("status").should("eq", "rejected");
      cy.readRecord(test, ["status"]).its("status").should("eq", "testing");
      testingTasks(test).then(([done, retest, ...others]) => {
        expect(others).to.be.empty;
        expect(done.status).to.equal("done");
        expect(retest.status).to.equal("open");
        expect(retest.assignee_id).to.equal(false);
        expect(retest.note).to.contain(reason);
      });

      cy.signInAs("tester");
      enterResult(test, "0.009");
      results(test).then((rows) => {
        expect(rows.map((row) => [row.status, row.is_reported])).to.deep.equal([
          ["none", true],
          ["rejected", false],
        ]);
      });
    });
  });

  it("TC-WF04-A1 lets the tester confirm the suggested text for a value below the LOD, keeping the measured value", () => {
    assignedTest("lead", { days: 7, sample: COMPARED_WATER }).then((test) => {
      cy.signInAs("tester");
      enterResult(test, "0.003");
      cy.get(".o_field_widget[name=limit_max]").should("contain", "0.01");
      cy.get(".o_field_widget[name=limit_unit_id]").should("contain", "mg/L");
      results(test).then(([result]) => {
        cy.readRecord(result, ["lod", "unit_id"]).then(({ lod, unit_id: [, unit] }) => {
          const text = `<${lod} ${unit} (below LOD)`;
          cy.get(".o_field_widget[name=value_suggestion]").should("have.text", text);
          cy.get("button[name=action_use_value_suggestion]").click();
          cy.get(".o_field_widget[name=value_text] input").should("have.value", text);
          cy.get(".o_field_widget[name=value_suggestion]").should("not.exist");
          cy.readRecord(result, ["value", "value_text", "conclusion"]).should("deep.include", {
            value: 0.003,
            value_text: text,
            conclusion: false,
          });
        });
        assess("Pass");
        cy.signRecord();
        cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
        cy.readRecord(result, ["status", "conclusion"]).should("deep.include", {
          status: "requested",
          conclusion: "pass",
        });
      });
    });
  });

  it("TC-WF04-A4 shows a missing exact-type limit and lets the tester send it only as insufficient basis", () => {
    assignedTest("lead", { days: 7, sample: LETTUCE_WITHOUT_LIMIT }).then((test) => {
      cy.signInAs("tester");
      enterResult(test, "0.12");
      cy.contains(".o_form_view .alert-warning", "can only be assessed as insufficient basis").should("be.visible");
      results(test).then(([result]) => {
        callRefused("medilab.test.result", "write", [[result.id], { conclusion: "pass" }]).should("contain", "insufficient basis");
        assess("Insufficient Basis");
        cy.signRecord();
        cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
        cy.readRecord(result, ["status", "conclusion", "limit_missing"]).should("deep.include", {
          status: "requested",
          conclusion: "insufficient",
          limit_missing: true,
        });
      });
    });
  });

  it("TC-WF04-A1 lets the tester enter and send a plain text result on a sample without a regulation", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.signRecord("action_enter_result");
      cy.get(".o_field_widget[name=conclusion]").should("not.exist");
      cy.get(".o_field_widget[name=value_text] input").type("Not detected").blur();
      cy.get(".o_field_widget[name=value]").should("not.exist");
      save();
      cy.signRecord();
      cy.get(`${ACTIONS} button[name=action_withdraw]:visible`).should("exist");
      results(test).then(([result]) =>
        cy.readRecord(result, ["status", "value_display"]).should("deep.include", { status: "requested", value_display: "Not detected" }),
      );
    });
  });

  it("TC-WF04-E3 lets the head cancel a test with a reason, and completes the sample and its report without it", () => {
    leadInTesting().then((sample) => {
      const { lead, ph } = sample;
      approvedResult(ph, { value: 7.2 }).as("phResult");
      cy.signInAs("head_of_department");
      cy.openRecord(lead);
      cy.rejectRecord(CANCELLATION, { action: "action_cancel" });
      cy.get(".o_field_widget[name=cancel_reason]").should("contain", CANCELLATION);
      cy.readRecord(lead, ["status", "cancel_reason"]).should("deep.include", { status: "cancelled", cancel_reason: CANCELLATION });
      cy.readRecord(lead.task, ["status"]).its("status").should("eq", "cancelled");
      cy.readRecord(lead.booking, ["status"]).its("status").should("eq", "cancelled");
      cy.readRecord(sample, ["status"]).its("status").should("eq", "completed");
      cy.readRecord(sample, ["request_id"]).then(({ request_id: [requestId] }) =>
        cy
          .get("@phResult")
          .then((phResult) =>
            callAs(LAB_HEAD, "medilab.test.report", "search_read", [[["request_id", "=", requestId]]], { fields: ["result_ids"] }).should(
              ([report]) => expect(report.result_ids).to.deep.equal([phResult.id]),
            ),
          ),
      );
    });
  });
});

describe("WF-04 feature acceptance criteria", () => {
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

  it("TC-F30-01 shows the tester the steps of the method on their testing task, in number order", () => {
    bookedLead().then((test) => {
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

  it("TC-F32-02 keeps a result's copied limit when the regulation changes, and holds one limit per parameter and sample type", () => {
    newRegulation(0.05).then((regulation) => {
      assignedTest("lead", { days: 7, sample: { regulation } }).then((test) => {
        enteredResult(test, { value: 0.004 }).then((result) => {
          cy.signInAs("administrator");
          cy.openRecord(regulation);
          cy.expectRefusal({
            read: () => cy.readRecord(regulation, ["limit_ids", "write_date"]),
            action: () => {
              addLine("limit_ids");
              pick("parameter_id", "Lead (Pb)");
              pick("sample_type_id", "Bottled water");
              cy.get(".o_selected_row [name=limit_text] input").type("Không phát hiện");
              cy.get(".o_form_button_save").click();
            },
            message: "A regulation sets at most one limit per parameter and sample type.",
          });
          discardRefused();
          cy.get(".o_field_widget[name=limit_ids] .o_data_row td[name=max_value]").click();
          cy.get(".o_selected_row [name=max_value] input").clear().type("0.02");
          saveAndWait("medilab.regulation");
          cy.readRecord(regulation, ["limit_ids"]).then(({ limit_ids: [limit] }) =>
            cy.readRecord({ model: "medilab.regulation.limit", id: limit }, ["max_value"]).its("max_value").should("eq", 0.02),
          );
          cy.readRecord(result, ["limit_max"]).its("limit_max").should("eq", 0.05);
        });
      });
    });
  });

  it("TC-F32-03 refuses to send a result whose requested comparison has no conclusion", () => {
    assignedTest("lead", { days: 7, sample: COMPARED_WATER }).then((test) => {
      enteredResult(test, { value: 0.004 }).then((result) => {
        cy.signInAs("tester");
        cy.openRecord(result);
        cy.expectRefusal({
          read: () => cy.readRecord(result, ["status", "value", "conclusion", "write_date"]),
          action: () => cy.signRecord(),
          message: "Assess the result against the regulation as pass, fail or insufficient basis before sending it.",
        });
      });
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

  it("TC-F34-02 sends only the latest result of a test for approval", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      enteredResult(test, { value: 0.004 }).then((first) => {
        enteredResult(test, { value: 0.005 });
        cy.signInAs("tester");
        cy.openRecord(first);
        cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
        callRefused("medilab.test.result", "action_sign", [[first.id]]).should(
          "eq",
          "Only the reported result of a sample test is sent for approval.",
        );
        cy.readRecord(first, ["status", "is_reported"]).should("deep.include", { status: "none", is_reported: false });
      });
    });
  });

  it("TC-F36-03 refuses to cancel a test without a reason, or a test with an approved result", () => {
    assignedTest("lead", { days: 7 }).then((test) => {
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.expectRefusal({
        read: () => cy.readRecord(test, ["status", "cancel_reason", "write_date"]),
        action: () => {
          cy.get(`${ACTIONS} button.btn-danger:visible`).click();
          cy.get(".modal:visible [name=reason] textarea").type("   ");
          cy.get(".modal:visible button[name=action_cancel]").click();
        },
        message: "Give a reason for cancelling the test.",
      });
    });
    assignedTest("lead", { days: 7 }).then((test) => {
      approvedResult(test, { value: 0.004 });
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      cy.get(`${ACTIONS} button.btn-danger`).should("not.exist");
      callRefused("medilab.sample.test", "action_cancel", [[test.id], CANCELLATION]).should(
        "match",
        /^Only a waiting, assigned or testing sample test can be cancelled: /,
      );
      cy.readRecord(test, ["status"]).its("status").should("eq", "approved");
    });
  });
});

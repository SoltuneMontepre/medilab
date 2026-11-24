import { choose, newRecord, openMenu, openRow, openTab, pick, save, search } from "../../../support/form";
import { MENU } from "../../../support/menus";
import { onPhone, signedInPhone } from "../../../support/mobile";
import { callAs, callRefused, refAs } from "../../../support/odoo";
import { step } from "../../../support/steps";
import { sentDispatch } from "../wf-05-outsourced-testing/setup";
import { PARAMETERS, PNG, STAFF, collectionTask, draftRecord, inMinutes, orderCollectionTask, orderRequest, receive, signedRecord, staffRequest, testingTasks } from "./setup";

const HEAD = "demo.head_of_department";
const SALES = "demo.sales";

// Sample delivery staff record a sample's receipt on its open form.
function fillReceipt(condition, note) {
  cy.get(".o_field_widget[name=received_quantity] input").type("500 ml");
  choose("condition", condition);
  if (note) {
    cy.get(".o_field_widget[name=condition_note] textarea").type(note);
  }
  cy.get(".o_field_widget[name=storage_location] input").type("Tủ lạnh 2");
}

// Sample delivery staff record a sample's receipt on its form.
function receiveOnForm(sample, condition, note) {
  cy.openRecord(sample);
  fillReceipt(condition, note);
}

// Sample delivery staff fill in a handover record of one sample on the web, adjusting the expected samples to the
// `actual` ones handed over and noting `excess` material when given. `list` opens the list of handover records.
function fillHandoverRecord(request, sample, quantity, { actual, excess, list = "/odoo/handover-records" } = {}) {
  newRecord(list);
  pick("request_id", request.code);
  cy.get(".o_field_widget[name=handed_over_by_name] input").type("Phạm Thị Hoa");
  pick("received_by_id", "Vo Van Tai");
  cy.get(".o_field_widget[name=sample_ids] .o_field_x2many_list_row_add button").click();
  pick("sample_id", sample.code);
  if (actual) {
    cy.get(".o_selected_row .o_field_widget[name=actual_count] input").clear().type(String(actual));
  }
  cy.get(".o_selected_row .o_field_widget[name=quantity] input").type(quantity);
  if (excess) {
    cy.get(".o_selected_row .o_field_widget[name=excess_material] input").type(excess);
  }
  choose("condition", "Good");
  save();
  return cy.location("pathname").then((path) => ({ model: "medilab.handover.record", id: Number(path.split("/").pop()) }));
}

// Sample delivery staff claim the collection task a request to collect the sample again queued for them, collect it and
// receive the sample brought back.
function collectAgain(sample) {
  const name = `Collect ${sample.code} again`;
  cy.signInAs("sample_delivery_staff");
  cy.visit("/odoo/awaiting-tasks");
  search(name);
  cy.contains(".o_data_row", name).find("button[name=action_claim]").click();
  cy.contains(".o_data_row", name).should("not.exist");
  cy.visit("/odoo/my-tasks");
  search(name);
  cy.contains(".o_data_row", name).click();
  cy.get(".o_field_widget[name=received_quantity] input").clear().type("500 ml");
  cy.get(".o_statusbar_buttons button[name=action_receive_more_entered]").click();
  cy.get(".o_statusbar_buttons button[name=action_receive_more_entered]").should("not.exist");
}

// A person of a department scans the sample's label to record that the department received it; `open` opens the scan.
function scanLabel(code, open = () => cy.visit("/odoo/action-sol_laboratory.action_medilab_sample_scan")) {
  open();
  cy.get(".modal .o_field_widget[name=code] input").type(code);
  cy.get(".modal button[name=action_confirm]").click();
}

// A department's receipt of a sample, once its label has been scanned; the scan opens again for the next label.
function scanned(code, open) {
  scanLabel(code, open);
  cy.contains(".o_notification", code).should("be.visible");
}

describe("WF-02 Sample reception and handover", () => {
  it("TC-WF02-M receives, labels and hands over a sample the customer brings", () => {
    orderRequest().then((request) => {
      const [sample] = request.samples;
      step("Sample delivery staff open the sample the customer brings");
      cy.signInAs("sample_delivery_staff");
      // Only the request of an order goes through the paid step.
      cy.readRecord(request, ["status"]).its("status").should("eq", "paid");
      openMenu(MENU.laboratory, MENU.samples, MENU.sampleList);
      openRow(sample.code);
      step("Staff check the expected containers and record the sample's receipt");
      // Staff see the containers expected from the accepted quotation before they record the actual handover.
      openTab("expected_sampling");
      cy.get(".o_field_widget[name=expected_sample_count]").should("contain", "1");
      cy.get(".o_field_widget[name=expected_sampling_ids] .o_data_row").should("have.length", 1).and("contain", "Polyethylene bottle");
      fillReceipt("Good");
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").click();
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").should("not.exist");
      cy.readRecord(sample, ["status"]).its("status").should("eq", "received");
      cy.readRecord(request, ["status"]).its("status").should("eq", "sample_received");

      step("Staff print the labels of the test request");
      openMenu(MENU.laboratory, MENU.requests, MENU.testRequests);
      openRow(request.code);
      cy.intercept("POST", "/report/download").as("labels");
      cy.get(".o_statusbar_buttons button[name=action_print_labels]").click();
      cy.wait("@labels").its("response.statusCode").should("eq", 200);

      step("Staff fill in the handover record, which the customer signs");
      fillHandoverRecord(request, sample, "500 ml", { list: () => openMenu(MENU.laboratory, MENU.samples, MENU.handoverRecords) }).then((record) => {
        // The customer signs on the phone of sample delivery staff.
        callAs(STAFF, "medilab.handover.record", "action_sign", [[record.id], PNG]);
        cy.reload();
        cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Signed");
      });

      step("The head of department scans the label, which queues the sample's testing task");
      cy.signInAs("head_of_department");
      scanned(sample.code, () => openMenu(MENU.laboratory, MENU.samples, MENU.scanLabel));
      cy.readRecord(sample, ["handover_ids"]).then(({ handover_ids }) =>
        cy.readRecord({ model: "medilab.sample.handover", id: handover_ids[0] }, ["received_at"]).its("received_at").should("be.a", "string"),
      );
      testingTasks(sample).should((tasks) => {
        expect(tasks, "testing tasks").to.have.length(1);
        expect(tasks[0].department_id[1]).to.equal("Chemistry");
        expect(tasks[0].status).to.equal("open");
      });
    });
  });

  it("TC-WF02-A1 collects the samples at the customer's site from the collection task, with photos and the customer's signature", () => {
    // Sales starts the collection on the confirmed order; the task waits in the queue of sample delivery staff.
    orderCollectionTask().then(({ request, task }) => {
      const [sample] = request.samples;
      step("Sample delivery staff claim the collection task from the queue");
      cy.signInAs("sample_delivery_staff");
      cy.visit("/odoo/awaiting-tasks");
      search(task.order);
      cy.contains(".o_data_row", task.name).find("button[name=action_claim]").click();
      cy.readRecord(task, ["status", "planned_start"]).should((read) => {
        expect(read.status).to.equal("assigned");
        expect(read.planned_start).to.equal(false);
      });
      step("Staff start the collection at the customer's site");
      cy.openRecord(task);
      cy.get(".o_statusbar_buttons button[name=action_start]").click();
      cy.get(".o_statusbar_buttons button[name=action_start]").should("not.exist");
      // The photo and the signature come from the phone of sample delivery staff.
      step("Staff photograph the sample, and the customer signs the handover record");
      callAs(STAFF, "medilab.sample", "action_attach_photo", [[sample.id], PNG, "collection.png"]);
      signedRecord(request, sample);
      step("Staff finish the collection task");
      cy.get(".o_statusbar_buttons button[name=action_done]").click();
      cy.get(".o_statusbar_buttons button[name=action_done]").should("not.exist");
      cy.readRecord(task, ["status"]).its("status").should("eq", "done");
      cy.readRecord(sample, ["photo_ids"]).its("photo_ids").should("have.length", 1);
    });
  });

  it("TC-F16-01 shows a planned collection task on the staff's schedule and to-do list, and reminds them before it starts", () => {
    staffRequest().then((request) => {
      // Inside the default reminder lead of 15 minutes.
      collectionTask(request, { planned_start: inMinutes(10), deadline: inMinutes(24 * 60) }).then((task) => {
        cy.signInAs("sample_delivery_staff");
        cy.visit("/odoo/my-tasks");
        search(task.name);
        cy.contains(".o_data_row", task.name).should("be.visible");
        cy.visit("/odoo/calendar");
        cy.contains(".fc-event", task.name).should("exist");

        refAs("demo.administrator", "sol_laboratory.ir_cron_notifications_remind").then(({ id }) =>
          callAs("demo.administrator", "ir.cron", "method_direct_trigger", [[id]]),
        );
        callAs("demo.administrator", "mail.message", "search_count", [
          [
            ["model", "=", "medilab.task"],
            ["res_id", "=", task.id],
            ["subtype_id.code", "=", "task.reminder"],
            ["notification_ids.res_partner_id.user_ids.login", "=", STAFF],
          ],
        ]).should("eq", 1);
      });
    });
  });

  it("TC-WF02-A3 hands a sample tested by two departments to both, and each records its own receipt", () => {
    staffRequest({ samples: [[PARAMETERS.lead, PARAMETERS.coliforms]] }).then(({ samples: [sample] }) => {
      step("Staff receive a sample that two departments test");
      receive(sample);
      step("Chemistry scans the label");
      cy.signInAs("head_of_department");
      scanned(sample.code);
      step("Microbiology scans the label");
      cy.signInAs("microbiology_tester");
      scanned(sample.code);
      step("The sample shows a handover to each department, with who received it");
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(sample);
      openTab("handovers");
      cy.get(".o_field_widget[name=handover_ids] .o_data_row").should("have.length", 2);
      for (const [department, person] of [
        ["Chemistry", "sol_demo.demo_person_head_of_department"],
        ["Microbiology", "sol_demo.demo_person_microbiology_tester"],
      ]) {
        refAs("demo.administrator", person)
          .then(({ id }) => callAs("demo.administrator", "medilab.person", "read", [[id], ["name"]]))
          .then(([{ name }]) => cy.contains(".o_field_widget[name=handover_ids] .o_data_row", department).should("contain", name));
      }
    });
  });

  it("TC-WF02-A4 puts an insufficient sample on hold until more is collected", () => {
    staffRequest().then((request) => {
      const [sample] = request.samples;
      step("Staff find the sample insufficient, which puts it on hold");
      receive(sample, "insufficient", "Chỉ có 50 ml.");
      // An insufficient sample is held before any receipt.
      callAs(STAFF, "medilab.sample", "read", [[sample.id], ["status", "received_at"]]).its("0").should("deep.include", { status: "on_hold", received_at: false });
      callAs(STAFF, "medilab.test.request", "read", [[request.id], ["status"]]).its("0.status").should("eq", "paid");
      step("The head of department is told");
      callAs("demo.administrator", "mail.message", "search_count", [
        [
          ["model", "=", "medilab.sample"],
          ["res_id", "=", sample.id],
          ["notification_ids.res_partner_id.user_ids.login", "=", "demo.head_of_department"],
        ],
      ]).should("eq", 1);
      step("The head asks for the sample to be collected again");
      cy.signInAs("head_of_department");
      cy.openRecord(sample);
      cy.get(".o_statusbar_buttons button[name=action_request_recollection]").click();
      cy.get(".o_field_widget[name=recollection_requested_at]").invoke("text").should("match", /\d/);
      refAs("demo.administrator", "sol_demo.demo_person_head_of_department").then((head) =>
        cy.readRecord(sample, ["recollection_requested_by_id"]).its("recollection_requested_by_id.0").should("eq", head.id),
      );

      step("Staff collect more sample, which is received and gets its testing task");
      collectAgain(sample);
      cy.readRecord(sample, ["status"]).its("status").should("eq", "received");
      cy.readRecord(request, ["status"]).its("status").should("eq", "sample_received");
      testingTasks(sample).should("have.length", 1);
    });
  });

  it("TC-WF02-A5 corrects a signed handover record with a new record and keeps the old one", () => {
    staffRequest().then((request) => {
      const [sample] = request.samples;
      receive(sample);
      step("A handover record with a wrong quantity is signed");
      signedRecord(request, sample, "50 ml").then((wrong) => {
        cy.signInAs("sample_delivery_staff");
        step("Staff record the correction on a new handover record, which the customer signs");
        fillHandoverRecord(request, sample, "500 ml").then((correction) => {
          callAs(STAFF, "medilab.handover.record", "action_sign", [[correction.id], PNG]);
          cy.readRecord(correction, ["status"]).its("status").should("eq", "signed");
        });
        step("The wrong record stays signed and unchanged");
        cy.readRecord(wrong, ["status", "sample_ids"]).then((read) => {
          expect(read.status).to.equal("signed");
          cy.readRecord({ model: "medilab.handover.record.sample", id: read.sample_ids[0] }, ["quantity"]).its("quantity").should("eq", "50 ml");
        });
      });
    });
  });

  it("TC-WF02-E1 rejects an unusable sample with its condition note and opens no testing task", () => {
    const note = "Chai bị nứt, mẫu bị rò rỉ.";
    staffRequest().then((request) => {
      const [sample] = request.samples;
      step("Sample delivery staff find the sample unusable");
      cy.signInAs("sample_delivery_staff");
      // The condition is decided first; an unusable one offers rejecting the sample, never receiving it.
      receiveOnForm(sample, "Unusable");
      cy.contains(".o_statusbar_buttons button", "Receive").should("not.exist");
      cy.contains(".o_statusbar_buttons button", "Reject").should("be.visible");
      step("Rejecting without saying why is refused");
      cy.expectRefusal({
        read: () => cy.readRecord(sample, ["status"]),
        action: () => cy.get(".o_statusbar_buttons button[name=action_receive_entered]").click(),
        message: "Enter why the sample cannot be tested.",
      });
      cy.get(".o_error_dialog .btn-primary, .modal .btn-close").first().click();
      step("Staff note why and reject the sample, which gets no testing task");
      cy.get(".o_field_widget[name=condition_note] textarea").type(note);
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").click();
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").should("not.exist");
      cy.readRecord(sample, ["status", "condition_note", "received_at"]).should((read) => {
        expect(read.status).to.equal("rejected");
        expect(read.condition_note).to.equal(note);
        expect(read.received_at, "received").to.equal(false);
      });
      cy.readRecord(request, ["status"]).its("status").should("eq", "paid");
      testingTasks(sample).should("be.empty");
    });
  });

  it("TC-WF02-E2 refuses a label scanned by a person outside the department that tests the sample", () => {
    staffRequest().then(({ samples: [sample] }) => {
      step("Staff receive the sample for Chemistry");
      receive(sample);
      step("Sample delivery staff, outside Chemistry, scan its label and are refused");
      cy.signInAs("sample_delivery_staff");
      cy.expectRefusal({
        read: () => cy.readRecord(sample, ["handover_ids"]).then(({ handover_ids }) => cy.readRecord({ model: "medilab.sample.handover", id: handover_ids[0] }, ["received_at"])),
        action: () => scanLabel(sample.code),
        message: `${sample.code} has no handover to Sample reception.`,
      });
    });
  });

  it("TC-WF02-E3 refuses to confirm a test request without a sample, or with a sample without a parameter", () => {
    staffRequest({ samples: [], confirm: false }).then((request) => {
      step("Confirming a test request without a sample is refused");
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(request);
      cy.expectRefusal({
        read: () => cy.readRecord(request, ["status", "write_date"]),
        action: () => cy.get(".o_statusbar_buttons button[name=action_confirm]").click(),
        message: `Test request ${request.code} needs at least one sample before it can be confirmed.`,
      });
    });
    step("Confirming one whose sample has no parameter is refused");
    staffRequest({ samples: [[]], confirm: false }).then((request) => {
      cy.openRecord(request);
      cy.expectRefusal({
        read: () => cy.readRecord(request, ["status", "write_date"]),
        action: () => cy.get(".o_statusbar_buttons button[name=action_confirm]").click(),
        message: `Add at least one parameter to ${request.samples[0].code} before confirming test request ${request.code}.`,
      });
    });
  });

  it("TC-WF02-E4 does not let anyone edit a signed handover record", () => {
    staffRequest().then((request) => {
      const [sample] = request.samples;
      receive(sample);
      step("The customer signs the handover record");
      signedRecord(request, sample).then((record) => {
        cy.signInAs("sample_delivery_staff");
        step("Its fields are read-only, and changing it is refused");
        cy.openRecord(record);
        cy.get(".o_field_widget[name=handed_over_by_name]").should("have.class", "o_readonly_modifier");
        cy.get(".o_field_widget[name=sample_ids]").should("have.class", "o_readonly_modifier");
        callRefused("medilab.handover.record", "write", [[record.id], { handed_over_by_name: "Người khác" }]).should(
          "eq",
          "A signed handover record cannot be changed. Create a new record instead.",
        );
      });
    });
  });

  it("TC-WF02-E5 asks again for a sample whose delivery to the subcontractor failed; it keeps its tests and gets no new testing task", () => {
    sentDispatch("lead").then(({ test, dispatch }) => {
      // The carrier could not deliver it.
      step("The delivery to the subcontractor fails and the dispatch is cancelled");
      callAs(HEAD, "medilab.subcontract.dispatch", "action_cancel", [[dispatch.id]]);
      callAs(HEAD, "medilab.sample.test", "read", [[test.id], ["sample_id"]]).then(([read]) => {
        const sample = { model: "medilab.sample", id: read.sample_id[0], code: test.code };
        testingTasks(sample).then((before) => {
          step("The head asks for the sample again, which goes on hold with its tests");
          cy.signInAs("head_of_department");
          cy.openRecord(sample);
          cy.get(".o_statusbar_buttons button[name=action_request_recollection]").click();
          cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "On Hold");
          cy.readRecord(sample, ["test_ids"]).its("test_ids").should("deep.equal", [test.id]);

          step("Staff collect it again; it keeps its code and testing tasks");
          collectAgain(sample);
          cy.readRecord(sample, ["status", "code"]).should("deep.include", { status: "testing", code: sample.code });
          testingTasks(sample).should((after) => expect(after.map((task) => task.id)).to.deep.equal(before.map((task) => task.id)));
        });
      });
    });
  });

  it("TC-WF02-E6 records extra samples and excess material on the handover the customer confirms, adding no test and changing no order", () => {
    orderRequest().then((request) => {
      const [sample] = request.samples;
      callAs(SALES, "sale.order", "search_read", [[["test_request_id", "=", request.id]]], { fields: ["order_line", "amount_total"] }).then(([before]) => {
        step("Staff record two samples and excess material on the handover record");
        cy.signInAs("sample_delivery_staff");
        cy.readRecord(sample, ["test_ids"]).then(({ test_ids: tests }) => {
          fillHandoverRecord(request, sample, "2 chai 500 ml", { actual: 2, excess: "Dư khoảng 300 ml so với lượng cần" }).then((record) => {
            cy.get(".o_field_widget[name=sample_ids] .o_data_row").should("contain", "Dư khoảng 300 ml so với lượng cần");
            step("The customer signs, confirming the extra sample and the excess");
            callAs(STAFF, "medilab.handover.record", "action_sign", [[record.id], PNG]);
            cy.readRecord(record, ["sample_ids"]).then(({ sample_ids: [line] }) =>
              cy
                .readRecord({ model: "medilab.handover.record.sample", id: line }, ["expected_count", "actual_count", "extra_count", "excess_material"])
                .should("deep.include", { expected_count: 1, actual_count: 2, extra_count: 1, excess_material: "Dư khoảng 300 ml so với lượng cần" }),
            );
          });
          step("No test is added, and the order is unchanged");
          cy.readRecord(sample, ["test_ids"]).its("test_ids").should("deep.equal", tests);
          callAs(SALES, "sale.order", "read", [[before.id], ["order_line", "amount_total"]]).its("0").should("deep.equal", before);
        });
      });
    });
  });

  it("TC-WF02-E7 keeps a sample not handed over expected until another collection records it on a record of its own", () => {
    staffRequest({ samples: [[PARAMETERS.lead], [PARAMETERS.lead]] }).then((request) => {
      const [first, second] = request.samples;
      step("The first sample is handed over on a signed record");
      signedRecord(request, first);
      step("The second sample, not handed over, stays expected");
      cy.signInAs("sample_delivery_staff");
      cy.readRecord(second, ["status", "handover_line_ids"]).should("deep.include", { status: "expected", handover_line_ids: [] });

      step("A later collection records it on a handover record of its own");
      fillHandoverRecord(request, second, "500 ml").then((later) => {
        callAs(STAFF, "medilab.handover.record", "action_sign", [[later.id], PNG]);
        cy.readRecord(second, ["handover_line_ids"]).its("handover_line_ids").should("have.length", 1);
        cy.readRecord(first, ["handover_line_ids"]).its("handover_line_ids").should("have.length", 1);
      });
    });
  });
});

describe("WF-02 feature acceptance criteria", () => {
  it("TC-F15-02 gives each sample its own lab code of the month", () => {
    staffRequest({ samples: [[PARAMETERS.lead], [PARAMETERS.lead]] }).then(({ samples }) => {
      expect(samples.map((sample) => sample.code)).to.satisfy((codes) => codes.every((code) => /^PTN\.\d{2}\.\d{2}\.\d{4}$/.test(code)));
      expect(new Set(samples.map((sample) => sample.code)).size).to.equal(2);
    });
  });

  it("TC-F15-03 shows testers only the lab code of a sample", () => {
    staffRequest().then(({ samples: [sample] }) => {
      receive(sample);
      cy.signInAs("tester");
      cy.openRecord(sample);
      cy.get(".o_field_widget[name=code]").should("contain", sample.code);
      cy.get(".o_field_widget[name=customer_sample_name]").should("not.exist");
      callRefused("medilab.sample", "read", [[sample.id], ["customer_sample_name"]]).should("contain", "customer_sample_name");
    });
  });

  it("TC-F16-02 stores the signature, time and device of a signed handover record and e-mails its PDF", () => {
    staffRequest().then((request) => {
      const [sample] = request.samples;
      receive(sample);
      // The customer signs on the phone of sample delivery staff, which MediLab records itself.
      draftRecord(request, sample).then((id) =>
        signedInPhone(STAFF).then((key) =>
          onPhone(key, "POST", `/handover-records/${id}/sign`, { signature: PNG, confirmed: true }).then(({ body: signed }) => {
            cy.signInAs("sample_delivery_staff");
            cy.readRecord({ model: "medilab.handover.record", id }, ["signature_attachment_id", "signed_at", "signed_device_id", "attachment_id", "sent_at"]).should((read) => {
              expect(read.signature_attachment_id, "signature").to.be.an("array");
              expect(read.signed_at, "signed at").to.be.a("string");
              expect(read.signed_device_id[1], "device").to.equal(signed.signed_device);
              expect(read.attachment_id, "PDF").to.be.an("array");
              expect(read.sent_at, "e-mailed").to.be.a("string");
            });
          }),
        ),
      );
    });
  });

  it("TC-F17-02 prints a label with the lab code, request code, due date and QR code, never the customer", () => {
    staffRequest({ expectedDate: "2099-12-31" }).then(({ code, samples: [sample] }) => {
      cy.signInAs("sample_delivery_staff");
      cy.request(`/report/html/sol_laboratory.report_sample_label/${sample.id}`)
        .its("body")
        .should((html) => {
          expect(html).to.contain(sample.code);
          expect(html).to.contain(code);
          expect(html).to.match(/Due<\/span>\s*<span>[^<]*\d{4}/);
          expect(html).to.match(/<img[^>]+(barcode|qr)/i);
          expect(html).not.to.contain("Nước Uống Sạch");
          expect(html).not.to.contain("Nước đóng chai");
        });
    });
  });

});

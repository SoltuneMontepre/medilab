import { choose, newRecord, openTab, pick, save, search } from "../../../support/form";
import { callAs, callRefused, refAs } from "../../../support/odoo";
import { PARAMETERS, PNG, STAFF, collectionTask, inMinutes, orderCollectionTask, orderRequest, receive, signedRecord, staffRequest, testingTasks } from "./setup";

// Sample delivery staff record a sample's receipt on its form.
function receiveOnForm(sample, condition, note) {
  cy.openRecord(sample);
  cy.get(".o_field_widget[name=received_quantity] input").type("500 ml");
  choose("condition", condition);
  if (note) {
    cy.get(".o_field_widget[name=condition_note] textarea").type(note);
  }
  cy.get(".o_field_widget[name=storage_location] input").type("Tủ lạnh 2");
}

// Sample delivery staff fill in a handover record of one sample on the web.
function fillHandoverRecord(request, sample, quantity) {
  newRecord("/odoo/handover-records");
  pick("request_id", request.code);
  cy.get(".o_field_widget[name=handed_over_by_name] input").type("Phạm Thị Hoa");
  pick("received_by_id", "Vo Van Tai");
  cy.get(".o_field_widget[name=sample_ids] .o_field_x2many_list_row_add button").click();
  pick("sample_id", sample.code);
  cy.get(".o_selected_row .o_field_widget[name=quantity] input").type(quantity);
  choose("condition", "Good");
  save();
  return cy.location("pathname").then((path) => ({ model: "medilab.handover.record", id: Number(path.split("/").pop()) }));
}

// A person of a department scans the sample's label to record that the department received it.
function scanLabel(code) {
  cy.visit("/odoo/action-sol_laboratory.action_medilab_sample_scan");
  cy.get(".modal .o_field_widget[name=code] input").type(code);
  cy.get(".modal button[name=action_confirm]").click();
}

// A department's receipt of a sample, once its label has been scanned.
function scanned(code) {
  scanLabel(code);
  cy.get(".modal").should("not.exist");
}

describe("WF-02 Sample reception and handover", () => {
  it("TC-WF02-M receives, labels and hands over a sample the customer brings", () => {
    orderRequest().then((request) => {
      const [sample] = request.samples;
      cy.signInAs("sample_delivery_staff");
      // Only the request of an order goes through the paid step.
      cy.readRecord(request, ["status"]).its("status").should("eq", "paid");
      receiveOnForm(sample, "Good");
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").click();
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").should("not.exist");
      cy.readRecord(sample, ["status"]).its("status").should("eq", "received");
      cy.readRecord(request, ["status"]).its("status").should("eq", "sample_received");

      cy.openRecord(request);
      cy.intercept("POST", "/report/download").as("labels");
      cy.get(".o_statusbar_buttons button[name=action_print_labels]").click();
      cy.wait("@labels").its("response.statusCode").should("eq", 200);

      fillHandoverRecord(request, sample, "500 ml").then((record) => {
        // The customer signs on the phone of sample delivery staff.
        callAs(STAFF, "medilab.handover.record", "action_sign", [[record.id], PNG]);
        cy.reload();
        cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Signed");
      });

      cy.signInAs("head_of_department");
      scanned(sample.code);
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
      cy.signInAs("sample_delivery_staff");
      cy.visit("/odoo/awaiting-tasks");
      search(task.order);
      cy.contains(".o_data_row", task.name).find("button[name=action_claim]").click();
      cy.readRecord(task, ["status", "planned_start"]).should((read) => {
        expect(read.status).to.equal("assigned");
        expect(read.planned_start).to.equal(false);
      });
      cy.openRecord(task);
      cy.get(".o_statusbar_buttons button[name=action_start]").click();
      cy.get(".o_statusbar_buttons button[name=action_start]").should("not.exist");
      // The photo and the signature come from the phone of sample delivery staff.
      callAs(STAFF, "medilab.sample", "action_attach_photo", [[sample.id], PNG, "collection.png"]);
      signedRecord(request, sample);
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

  it("TC-WF02-A2 lets sample delivery staff create a test request without an order, which skips the paid step", () => {
    cy.signInAs("sample_delivery_staff");
    newRecord("/odoo/test-requests");
    pick("customer_id", "Nước Uống Sạch");
    choose("delivery_method", "By Email");
    pick("report_recipient_id", "Phạm Thị Hoa");
    // The 15th of next month leaves time for the tests of the sample added below.
    cy.get(".o_field_widget[name=expected_date] input").click();
    cy.get(".o_datetime_picker .o_header_part")
      .invoke("text")
      .then((month) => {
        cy.get(".o_datetime_picker .o_next").click();
        cy.get(".o_datetime_picker .o_header_part").should("not.have.text", month);
      });
    cy.contains(".o_datetime_picker .o_date_item_cell:not(.o_out_of_range)", /^15$/).click();
    // A sample needs its saved test request.
    save();
    cy.get(".o_field_widget[name=sample_ids] .o_field_x2many_list_row_add button").click();
    cy.get(".modal .o_field_widget[name=customer_sample_name] input").type("Nước đóng chai 1");
    pick("sample_type_id", "Bottled water");
    choose("physical_state", "Liquid");
    cy.get(".modal .o_field_widget[name=test_ids] .o_field_x2many_list_row_add button").click();
    pick("parameter_id", "Lead (Pb)");
    cy.contains(".modal footer button", "Save & Close").click();
    cy.get(".modal").should("not.exist");
    cy.get(".o_statusbar_buttons button[name=action_confirm]").click();
    cy.get(".o_statusbar_buttons button[name=action_confirm]").should("not.exist");
    cy.location("pathname").then((path) => {
      const request = { model: "medilab.test.request", id: Number(path.split("/").pop()) };
      cy.readRecord(request, ["status", "sample_ids", "expected_date", "delivery_method", "report_recipient_id"]).then((read) => {
        expect(read.status).to.equal("confirmed");
        expect(read.expected_date).to.match(/-15$/);
        expect(read.delivery_method).to.equal("email");
        expect(read.report_recipient_id[1]).to.contain("Phạm Thị Hoa");
        receive({ id: read.sample_ids[0] });
        cy.readRecord(request, ["status"]).its("status").should("eq", "sample_received");
      });
    });
  });

  it("TC-WF02-A3 hands a sample tested by two departments to both, and each records its own receipt", () => {
    staffRequest({ samples: [[PARAMETERS.lead, PARAMETERS.coliforms]] }).then(({ samples: [sample] }) => {
      receive(sample);
      cy.signInAs("head_of_department");
      scanned(sample.code);
      cy.signInAs("microbiology_tester");
      scanned(sample.code);
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
    staffRequest().then(({ samples: [sample] }) => {
      receive(sample, "insufficient", "Chỉ có 50 ml.");
      callAs(STAFF, "medilab.sample", "read", [[sample.id], ["status"]]).its("0.status").should("eq", "on_hold");
      callAs("demo.administrator", "mail.message", "search_count", [
        [
          ["model", "=", "medilab.sample"],
          ["res_id", "=", sample.id],
          ["notification_ids.res_partner_id.user_ids.login", "=", "demo.head_of_department"],
        ],
      ]).should("eq", 1);
      cy.signInAs("head_of_department");
      cy.openRecord(sample);
      cy.get(".o_statusbar_buttons button[name=action_request_recollection]").click();
      cy.get(".o_field_widget[name=recollection_requested_at]").invoke("text").should("match", /\d/);
      refAs("demo.administrator", "sol_demo.demo_person_head_of_department").then((head) =>
        cy.readRecord(sample, ["recollection_requested_by_id"]).its("recollection_requested_by_id.0").should("eq", head.id),
      );

      cy.signInAs("sample_delivery_staff");
      cy.visit("/odoo/my-tasks");
      search(`Collect ${sample.code} again`);
      cy.contains(".o_data_row", `Collect ${sample.code} again`).click();
      cy.get(".o_field_widget[name=received_quantity] input").clear().type("500 ml");
      cy.get(".o_statusbar_buttons button[name=action_receive_more_entered]").click();
      cy.get(".o_statusbar_buttons button[name=action_receive_more_entered]").should("not.exist");
      cy.readRecord(sample, ["status"]).its("status").should("eq", "received");
      testingTasks(sample).should("have.length", 1);
    });
  });

  it("TC-WF02-A5 corrects a signed handover record with a new record and keeps the old one", () => {
    staffRequest().then((request) => {
      const [sample] = request.samples;
      receive(sample);
      signedRecord(request, sample, "50 ml").then((wrong) => {
        cy.signInAs("sample_delivery_staff");
        fillHandoverRecord(request, sample, "500 ml").then((correction) => {
          callAs(STAFF, "medilab.handover.record", "action_sign", [[correction.id], PNG]);
          cy.readRecord(correction, ["status"]).its("status").should("eq", "signed");
        });
        cy.readRecord(wrong, ["status", "sample_ids"]).then((read) => {
          expect(read.status).to.equal("signed");
          cy.readRecord({ model: "medilab.handover.record.sample", id: read.sample_ids[0] }, ["quantity"]).its("quantity").should("eq", "50 ml");
        });
      });
    });
  });

  it("TC-WF02-E1 rejects an unusable sample with its condition note and opens no testing task", () => {
    const note = "Chai bị nứt, mẫu bị rò rỉ.";
    staffRequest().then(({ samples: [sample] }) => {
      cy.signInAs("sample_delivery_staff");
      receiveOnForm(sample, "Damaged");
      cy.expectRefusal({
        read: () => cy.readRecord(sample, ["status"]),
        action: () => cy.get(".o_statusbar_buttons button[name=action_receive_entered]").click(),
        message: "Enter why the sample cannot be tested.",
      });
      cy.get(".o_error_dialog .btn-primary, .modal .btn-close").first().click();
      cy.get(".o_field_widget[name=condition_note] textarea").type(note);
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").click();
      cy.get(".o_statusbar_buttons button[name=action_receive_entered]").should("not.exist");
      cy.readRecord(sample, ["status", "condition_note"]).should((read) => {
        expect(read.status).to.equal("rejected");
        expect(read.condition_note).to.equal(note);
      });
      testingTasks(sample).should("be.empty");
    });
  });

  it("TC-WF02-E2 refuses a label scanned by a person outside the department that tests the sample", () => {
    staffRequest().then(({ samples: [sample] }) => {
      receive(sample);
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
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(request);
      cy.expectRefusal({
        read: () => cy.readRecord(request, ["status", "write_date"]),
        action: () => cy.get(".o_statusbar_buttons button[name=action_confirm]").click(),
        message: `Test request ${request.code} needs at least one sample before it can be confirmed.`,
      });
    });
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
      signedRecord(request, sample).then((record) => {
        cy.signInAs("sample_delivery_staff");
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
});

describe("WF-02 feature acceptance criteria", () => {
  it("TC-F15-02 gives each sample its own lab code of the year", () => {
    staffRequest({ samples: [[PARAMETERS.lead], [PARAMETERS.lead]] }).then(({ samples }) => {
      // Codes take the year where the laboratory works, which can differ from the test runner's.
      const year = new Intl.DateTimeFormat("en", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric" }).format(new Date());
      expect(samples.map((sample) => sample.code)).to.satisfy((codes) => codes.every((code) => code.startsWith(`PTN.${year}.`)));
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
      refAs(STAFF, "sol_demo.demo_mobile_device_sample_delivery_staff").then((device) =>
        signedRecord(request, sample, "500 ml", device.id).then((record) => {
          cy.signInAs("sample_delivery_staff");
          cy.readRecord(record, ["signature_attachment_id", "signed_at", "signed_device_id", "attachment_id", "sent_at"]).should((read) => {
            expect(read.signature_attachment_id, "signature").to.be.an("array");
            expect(read.signed_at, "signed at").to.be.a("string");
            expect(read.signed_device_id[0], "device").to.equal(device.id);
            expect(read.attachment_id, "PDF").to.be.an("array");
            expect(read.sent_at, "e-mailed").to.be.a("string");
          });
        }),
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
        callRefused("medilab.person", "write", [[person.id], { team_id: pathogens.id }]).should("match", /^Pathogens is not a team of the department of /);
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
});

import { pick, search } from "../../../support/form";
import { callAs, callRefused, refAs } from "../../../support/odoo";
import { orderAt } from "../wf-01-order-to-test-request/setup";
import { HEAD, LAB_HEAD, PARAMETERS, STAFF, approveTests, draftReport, issuedReport, receiveRequest } from "./setup";

const ADMIN = "demo.administrator";

// The message raised for a report, by its event: `issued` tells the customer, `delivered` e-mails the PDF. With
// `partnerId`, only a message that notifies that partner.
const reportMessage = (report, event, partnerId) =>
  callAs(ADMIN, "mail.message", "search_read", [
    [["notification_key", "=", `test_report:${report.id}:${event}`], ...(partnerId ? [["notification_ids.res_partner_id", "=", partnerId]] : [])],
  ], { fields: ["subject", "attachment_ids"] });

// The body of the rendered report, as the signed-in user prints it.
const reportHtml = (report) =>
  cy.request(`/report/html/sol_laboratory.report_test_report/${report.id}`).then(({ body }) => body.split("<main")[1]);

// Demo people's names, in the order of their external IDs.
const personNames = (...xmlIds) =>
  callAs(ADMIN, "ir.model.data", "search_read", [[["module", "=", "sol_demo"], ["name", "in", xmlIds.map((xmlId) => xmlId.split(".")[1])]]], {
    fields: ["name", "res_id"],
  }).then((rows) =>
    callAs(ADMIN, "medilab.person", "read", [xmlIds.map((xmlId) => rows.find((row) => `sol_demo.${row.name}` === xmlId).res_id), ["name"]]).then((people) =>
      people.map((person) => person.name),
    ),
  );

// The lab head signs the report on its form and confirms.
function signOnForm(report) {
  cy.signInAs("lab_head");
  cy.openRecord(report);
  cy.get(".o_statusbar_buttons button[name=action_sign]").click();
  cy.get(".modal-footer .btn-primary").click();
  cy.get(".o_statusbar_buttons button[name=action_sign]").should("not.exist");
}

// Sample delivery staff record the delivery of an issued report from the reports waiting for delivery.
function deliverFromList(code) {
  cy.signInAs("sample_delivery_staff");
  cy.visit("/odoo/reports-to-deliver");
  search(code);
  cy.contains(".o_data_row", code).find("button[name=action_record_delivery]").click();
  cy.contains(".o_data_row", code).should("not.exist");
}

// Digital signing is on in the settings, or off.
const setDigitalSigning = (enabled) =>
  callAs(ADMIN, "res.config.settings", "create", [{ digital_signing_enabled: enabled }]).then((id) =>
    callAs(ADMIN, "res.config.settings", "execute", [[id]]),
  );

describe("WF-06 Report signing, release and delivery", () => {
  it("TC-WF06-M signs the report, delivers it by e-mail and lets the customer download it", () => {
    refAs(ADMIN, "sol_demo.demo_res_partner_nuoc_sach").then((customer) =>
      refAs(ADMIN, "sol_demo.demo_res_partner_hoa").then((hoa) =>
      draftReport({ delivery_method: "email", report_recipient_id: hoa.id }).then(({ request, report }) => {
        signOnForm(report);
        cy.readRecord(report, ["status", "code", "attachment_id"]).then((issued) => {
          expect(issued.status).to.equal("issued");
          expect(issued.code).to.match(/^PKQ\.\d{4}\.\d+$/);
          expect(issued.attachment_id[1]).to.equal(`${issued.code}.pdf`);
          cy.readRecord(request, ["status"]).its("status").should("eq", "reported");
          reportMessage(report, "issued", customer.id).its("0.subject").should("eq", issued.code);

          deliverFromList(issued.code);
          personNames("sol_demo.demo_person_sample_delivery_staff").then(([staff]) =>
            cy.readRecord(report, ["delivered_by_id"]).its("delivered_by_id.1").should("eq", staff),
          );
          reportMessage(report, "delivered", hoa.id).should(([message]) => {
            expect(message, "e-mail to the recipient").to.exist;
            expect(message.attachment_ids, "PDF").to.include(issued.attachment_id[0]);
          });

          cy.signInAs("customer");
          cy.visit("/my/test-reports");
          cy.contains("main", issued.code).should("be.visible");
          cy.request(`/my/test-reports/${report.id}/download`).its("headers.content-type").should("contain", "application/pdf");
        });
      }),
      ),
    );
  });

  it("TC-WF06-A1 records a delivery in person or by post without sending an e-mail", () => {
    for (const values of [{ delivery_method: "in_person" }, { delivery_method: "post", delivery_note: "Gửi bưu điện đến 12 Nguyễn Huệ, Quận 1" }]) {
      issuedReport(values).then(({ report }) => {
        cy.signInAs("sample_delivery_staff");
        cy.openRecord(report);
        cy.get(".o_statusbar_buttons button[name=action_record_delivery]").click();
        cy.get(".o_statusbar_buttons button[name=action_record_delivery]").should("not.exist");
        cy.readRecord(report, ["delivery_method", "delivered_at"]).should((read) => {
          expect(read.delivery_method).to.equal(values.delivery_method);
          expect(read.delivered_at).to.be.a("string");
        });
        reportMessage(report, "delivered").should("be.empty");
      });
    }
  });

  it("TC-WF06-A2 issues the report in English, Vietnamese or both, as the request asks", () => {
    const headings = { en: "Test Report", vi: "Phiếu Kết Quả" };
    for (const language of ["en", "vi", "bilingual"]) {
      issuedReport({ report_language: language }).then(({ report }) => {
        cy.signInAs("lab_head");
        cy.readRecord(report, ["language"]).its("language").should("eq", language);
        reportHtml(report).should((html) => {
          if (language === "bilingual") {
            expect(html).to.contain(`${headings.vi} / ${headings.en}`);
          } else {
            expect(html).to.contain(headings[language]);
            expect(html).not.to.contain(headings[language === "en" ? "vi" : "en"]);
          }
        });
      });
    }
  });

  it("TC-WF06-A3 sends the named results back to their department, then signs the report once they are approved again", () => {
    const reason = "Lead reads above last month's blank; check the digestion blank and measure again.";
    draftReport().then(({ request, report }) => {
      cy.signInAs("lab_head");
      cy.openRecord(report);
      cy.contains(".o_statusbar_buttons button", "Reject").click();
      cy.get(".modal .o_field_widget[name=reason] textarea").type(reason);
      cy.get(".modal .o_field_widget[name=result_ids] input").type("Lead");
      cy.contains(".o-autocomplete--dropdown-item a", "Lead (Pb)").click();
      cy.get(".modal button[name=action_reject]").click();
      cy.get(".modal").should("not.exist");
      cy.readRecord(report, ["status", "result_ids"]).then((read) => {
        expect(read.status).to.equal("draft");
        callAs(HEAD, "medilab.test.result", "read", [read.result_ids, ["parameter_id", "status", "sample_test_id"]]).then((results) => {
          const lead = results.find((result) => result.parameter_id[1] === "Lead (Pb)");
          expect(lead.status, "lead result").to.equal("none");
          callAs(HEAD, "medilab.task", "search_read", [
            [
              ["document_model", "=", "medilab.sample.test"],
              ["document_id", "=", lead.sample_test_id[0]],
              ["status", "=", "open"],
            ],
          ], { fields: ["name", "note", "assignee_id"] }).then(([task]) => {
            expect(task.assignee_id, "unassigned").to.equal(false);
            expect(task.note).to.contain(reason);
            cy.signInAs("head_of_department");
            cy.visit("/odoo/department-queue");
            cy.contains(".o_searchview_facet", "Department").find(".o_facet_remove").click();
            search(task.name);
            cy.contains(".o_data_row", task.name).should("be.visible");
            approveAgain(lead);
          });
        });
      });
      callAs(LAB_HEAD, "medilab.test.request", "read", [[request.id], ["status"]]).its("0.status").should("eq", "completed");
      callAs(LAB_HEAD, "medilab.task", "search_read", [
        [
          ["document_model", "=", "medilab.test.report"],
          ["document_id", "=", report.id],
          ["status", "=", "open"],
        ],
      ], { fields: ["name"] }).should("have.length", 1);
      signOnForm(report);
      cy.readRecord(report, ["status"]).its("status").should("eq", "issued");
    });
  });

  it("TC-WF06-A4 issues the report of a request with a cancelled test without that test", () => {
    draftReport({ cancel: [PARAMETERS.ph] }).then(({ report }) => {
      signOnForm(report);
      cy.readRecord(report, ["status", "result_ids"]).then((read) => {
        expect(read.status).to.equal("issued");
        callAs(LAB_HEAD, "medilab.test.result", "read", [read.result_ids, ["parameter_id"]])
          .its("length")
          .should("eq", 1);
      });
      // The report names the approving head of department and the lab head, never the tester.
      personNames("sol_demo.demo_person_head_of_department", "sol_demo.demo_person_lab_head", "sol_demo.demo_person_tester").then(([head, labHead, tester]) =>
        reportHtml(report).should((html) => {
          expect(html).to.contain("Lead (Pb)");
          expect(html).not.to.match(/>\s*pH\s*</);
          expect(html).to.contain(head).and.contain(labHead);
          expect(html).not.to.contain(tester);
        }),
      );
    });
  });

  it("TC-WF06-A5 takes one portal order through reception, testing and approval to the issued report", () => {
    orderAt("approved").then((order) =>
      callAs("demo.sales", "sale.order", "read", [[order.id], ["name", "test_request_id"]]).then(([read]) => {
        const requestId = read.test_request_id[0];
        cy.signInAs("customer");
        cy.visit(`/orders/${order.id}`);
        cy.contains("main p", "Status:").should("contain", "Waiting");
        receiveRequest(requestId).then((tests) => approveTests(tests));
        callAs(LAB_HEAD, "medilab.test.report", "search", [[["request_id", "=", requestId]]]).then(([reportId]) => {
          const report = { model: "medilab.test.report", id: reportId };
          signOnForm(report);
          cy.readRecord(report, ["code"]).then(({ code }) => {
            // An order's results are announced on the order, to its contact.
            callAs(ADMIN, "mail.message", "search_count", [
              [
                ["model", "=", "sale.order"],
                ["res_id", "=", order.id],
                ["subject", "=", code],
              ],
            ]).should("eq", 1);
            cy.signInAs("customer");
            cy.visit("/my/test-reports");
            cy.contains("main", code).should("be.visible");
            // The issued report completes the order, which the customer rates once.
            cy.visit(`/orders/${order.id}`);
            cy.contains("main p", "Status:").should("contain", "Completed");
            cy.get("label[for=rating-5]").click();
            cy.get("textarea[name=comment]").type("Kết quả nhanh và rõ ràng.");
            cy.contains("button", "Send feedback").click();
            cy.contains("main", "Your rating: 5/5").should("be.visible");
            cy.get("textarea[name=comment]").should("not.exist");
            callRefused("sale.order", "action_give_feedback", [[order.id], 4, "Lần nữa"]).should("eq", "This order already has feedback.");
          });
        });
      }),
    );
  });

  describe("with digital signing on", () => {
    let signed;

    // Turned off, and the queued signature cancelled, even when the test fails, so later reports are issued without
    // Viettel Sign and nothing keeps retrying.
    afterEach(() => {
      setDigitalSigning(false);
      if (signed) {
        callAs(ADMIN, "medilab.job.item", "search", [
          [
            ["document_model", "=", "medilab.test.report"],
            ["document_id", "=", signed.id],
            ["status", "in", ["pending", "failed"]],
          ],
        ]).then((items) => items.length && callAs(ADMIN, "medilab.job.item", "action_cancel", [items]));
      }
    });

    it("TC-WF06-E1 keeps a report unsigned while Viettel Sign is unavailable, and retries the signature", () => {
      setDigitalSigning(true);
      draftReport().then(({ report }) => {
        signed = report;
        signOnForm(report);
        cy.contains(".alert-warning", "Viettel Sign has not signed the PDF yet.").should("be.visible");
        cy.readRecord(report, ["attachment_id", "digital_signature_id", "digital_signing_pending"]).should((read) => {
          expect(read.attachment_id, "PDF").to.equal(false);
          expect(read.digital_signature_id, "signature").to.equal(false);
          expect(read.digital_signing_pending, "pending").to.equal(true);
        });
        cy.expectRefusal({
          read: () => cy.readRecord(report, ["attachment_id", "digital_signing_pending"]),
          action: () => cy.get(".o_statusbar_buttons button[name=action_retry_digital_signing]").click(),
          message: "Viettel Sign could not sign the PDF. It is retried automatically.",
        });
        reportMessage(report, "issued").should("be.empty");
      });
    });
  });

  it("TC-WF06-E2 refuses to reject a report without a reason or without naming a result", () => {
    draftReport().then(({ report }) => {
      cy.signInAs("lab_head");
      cy.openRecord(report);
      cy.contains(".o_statusbar_buttons button", "Reject").click();
      cy.get(".modal .o_field_widget[name=reason] textarea").type("The blank is too high.");
      cy.expectRefusal({
        read: () => cy.readRecord(report, ["status", "write_date"]),
        action: () => cy.get(".modal button[name=action_reject]").click(),
        message: "Name the results to check again.",
      });
      cy.readRecord(report, ["result_ids"]).then(({ result_ids }) =>
        callRefused("medilab.test.report", "action_reject", [[report.id], "", result_ids]).should("eq", "A rejection needs a reason."),
      );
    });
  });

  it("TC-WF06-E3 refuses to deliver an unissued report, and lets a customer download only their own reports", () => {
    draftReport().then(({ report }) => {
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(report);
      cy.get(".o_statusbar_buttons button[name=action_record_delivery]").should("not.exist");
      callRefused("medilab.test.report", "action_record_delivery", [[report.id]]).should("match", /^Only an issued report not delivered yet can be delivered: /);
      callAs(LAB_HEAD, "medilab.test.report", "action_sign", [[report.id]]);
      cy.signInAs("individual");
      cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false }).its("status").should("eq", 404);
      cy.signInAs("customer");
      cy.request(`/my/test-reports/${report.id}/download`).its("status").should("eq", 200);
    });
  });
});

// The head of department gives the result sent back to the tester, who signs it again, and approves it, as in WF-04.
function approveAgain(result) {
  refAs(ADMIN, "sol_demo.demo_person_tester").then((tester) =>
    refAs(ADMIN, "sol_demo.demo_person_head_of_department").then((head) =>
      callAs(HEAD, "medilab.task", "search", [
        [
          ["document_model", "=", "medilab.sample.test"],
          ["document_id", "=", result.sample_test_id[0]],
          ["status", "=", "open"],
        ],
      ]).then((tasks) => callAs(HEAD, "medilab.task", "write", [tasks, { assignee_id: tester.id, assigned_by_id: head.id, status: "assigned" }])),
    ),
  );
  callAs("demo.tester", "medilab.test.result", "action_sign", [[result.id]]);
  callAs(HEAD, "medilab.test.result", "action_sign", [[result.id]]);
}

// A new testing method of Chemistry with a code no run has used, as `{ id, code }`.
function newMethod(prefix) {
  const code = `${prefix}-${Date.now()}`;
  return refAs(ADMIN, "sol_demo.demo_testing_field_chemistry").then((field) =>
    callAs(ADMIN, "medilab.testing.method", "create", [{ code, name: `Phương pháp ${code}`, field_id: field.id }]).then((id) => ({ id, code })),
  );
}

// A new accreditation certificate valid until `validUntil`, holding `methodIds`.
function newCertificate(methodIds = [], validUntil = "2099-12-31") {
  return callAs(ADMIN, "medilab.accreditation.certificate", "create", [
    { code: `VILAS-E2E-${Date.now()}`, issuing_body: "BoA", valid_until: validUntil, method_ids: [[6, 0, methodIds]] },
  ]).then((id) => ({ model: "medilab.accreditation.certificate", id }));
}

describe("WF-06 feature acceptance criteria", () => {
  it("TC-F41-01 links all 30 imported methods to the certificate and creates only the missing ones", () => {
    const stamp = Date.now();
    newCertificate().then((certificate) =>
      refAs(ADMIN, "sol_demo.demo_testing_field_chemistry").then((field) =>
        refAs(ADMIN, "sol_demo.demo_testing_method_tcvn_7602").then((first) =>
          refAs(ADMIN, "sol_demo.demo_testing_method_tcvn_6187_1").then((second) =>
            callAs(ADMIN, "medilab.testing.method", "read", [[first.id, second.id], ["code", "name"]], { context: { lang: "vi_VN" } }).then((known) => {
              // Two methods the laboratory already has, under other titles that must not replace theirs.
              const lines = [
                ...known.map((method) => ({ code: method.code, name: `Tên khác của ${method.code}` })),
                ...Array.from({ length: 28 }, (_, index) => ({ code: `E2E-${stamp}-${index + 1}`, name: `Phương pháp nhập ${index + 1}` })),
              ];
              callAs(ADMIN, "medilab.accreditation.certificate.import", "create", [
                { certificate_id: certificate.id, field_id: field.id, lang: "vi_VN", line_ids: lines.map((line) => [0, 0, line]) },
              ]).then((wizard) => callAs(ADMIN, "medilab.accreditation.certificate.import", "action_import", [[wizard]]));
              callAs(ADMIN, "medilab.testing.method", "read", [[first.id, second.id], ["name"]], { context: { lang: "vi_VN" } }).should((after) =>
                expect(after.map((method) => method.name)).to.deep.equal(known.map((method) => method.name)),
              );
              callAs(ADMIN, "medilab.testing.method", "search_count", [[["code", "=like", `E2E-${stamp}-%`]]]).should("eq", 28);
              cy.signInAs("administrator");
              cy.openRecord(certificate);
              cy.get(".o_field_widget[name=method_ids] .o_data_row").should("have.length", 30);
            }),
          ),
        ),
      ),
    );
  });

  describe("with ways of testing of a new method", () => {
    let ways = [];

    // Archived even when the test fails, so Lead keeps only its own ways of testing.
    afterEach(() => {
      if (ways.length) {
        callAs(ADMIN, "medilab.parameter.method", "action_archive", [ways]);
      }
    });

    it("TC-F41-02 accredits an in-house way of testing only while its method's certificate is valid, and never a subcontracted one", () => {
      newMethod("E2E-WAY").then((method) =>
        refAs(ADMIN, "sol_demo.demo_parameter_method_lead_aas").then((leadWay) =>
          callAs(ADMIN, "medilab.parameter.method", "read", [[leadWay.id], ["parameter_id", "unit_id", "department_id"]]).then(([way]) =>
            refAs(ADMIN, "sol_demo.demo_subcontractor_northern_testing").then((subcontractor) => {
              const values = { parameter_id: way.parameter_id[0], method_id: method.id, unit_id: way.unit_id[0] };
              callAs(ADMIN, "medilab.parameter.method", "create", [
                [
                  { ...values, department_id: way.department_id[0] },
                  { ...values, subcontractor_id: subcontractor.id },
                ],
              ]).then((created) => {
                ways = created;
                const [inHouse, subcontracted] = created;
                const readAccredited = () =>
                  callAs(ADMIN, "medilab.parameter.method", "read", [[inHouse, subcontracted], ["is_accredited"]]).then((ways) => ways.map((row) => row.is_accredited));
                newCertificate([method.id]).then((certificate) => {
                  readAccredited().should("deep.equal", [true, false]);
                  cy.signInAs("administrator");
                  cy.openRecord({ model: "medilab.parameter.method", id: inHouse });
                  cy.get(".o_field_widget[name=is_accredited] input").should("be.checked");
                  callAs(ADMIN, "medilab.accreditation.certificate", "write", [[certificate.id], { valid_until: "2000-01-01" }]);
                  readAccredited().should("deep.equal", [false, false]);
                });
              });
            }),
          ),
        ),
      );
    });
  });

  it("TC-F41-03 refuses an import with a row without a title and creates nothing", () => {
    const code = `E2E-BLANK-${Date.now()}`;
    newCertificate().then((certificate) => {
      cy.signInAs("administrator");
      cy.openRecord(certificate);
      cy.get("button[name=action_import_methods]").click();
      pick("field_id", "Chemistry");
      cy.get(".modal .o_field_x2many_list_row_add button").click();
      cy.get(".modal .o_selected_row .o_field_widget[name=code] input").type(code);
      cy.get(".modal .o_selected_row .o_field_widget[name=name] input").type("Phương pháp có tên");
      cy.get(".modal .o_field_x2many_list_row_add button").click();
      cy.get(".modal .o_data_row").should("have.length", 2);
      cy.get(".modal .o_data_row").eq(1).find(".o_field_widget[name=code] input").type(`${code}-2`);
      cy.expectRefusal({
        read: () => callAs(ADMIN, "medilab.testing.method", "search_count", [[["code", "=like", `${code}%`]]]),
        action: () => cy.get(".modal button[name=action_import]").click(),
        message: "Row 2 has no code or title. Nothing was imported.",
      });
    });
  });

  it("TC-F42-01 prints the mark of a valid quality registration after the parameter it covers", () => {
    issuedReport({ report_language: "en" }).then(({ report }) => {
      cy.signInAs("lab_head");
      reportHtml(report).should("match", /Lead \(Pb\)\s*\(\*\)/);
    });
  });

  it("TC-F42-03 prints no mark of a quality registration past its last valid day", () => {
    refAs(ADMIN, "sol_demo.demo_quality_registration_expired").then((registration) =>
      callAs(ADMIN, "medilab.quality.registration", "read", [[registration.id], ["valid_until", "report_mark"]]).then(([expired]) => {
        expect(new Date(expired.valid_until), "last valid day").to.be.below(new Date());
        issuedReport({ report_language: "en" }).then(({ report }) => {
          cy.signInAs("lab_head");
          // The expired registration covers pH.
          reportHtml(report).should((html) => {
            expect(html).to.contain("pH");
            expect(html).not.to.contain(expired.report_mark);
          });
        });
      }),
    );
  });

  it("TC-F44-01 shows who holds the lock of a document another user is editing, and still lets others read it", () => {
    draftReport().then(({ request }) => {
      callAs(STAFF, "medilab.test.request", "lock_take", [[request.id]]).its("taken").should("eq", true);
      cy.signInAs("administrator");
      cy.openRecord(request);
      personNames("sol_demo.demo_person_sample_delivery_staff").then(([staff]) => cy.contains(".o_form_view", "is editing").should("contain", staff));
      cy.get(".o_field_widget[name=customer_id] input").invoke("val").should("contain", "Nước Uống Sạch");
      callAs(STAFF, "medilab.test.request", "lock_release", [[request.id], "left"]);
    });
  });

  it("TC-F44-03 keeps a signed document read-only for everyone, administrators included", () => {
    draftReport().then(({ report }) =>
      callAs(LAB_HEAD, "medilab.test.report", "read", [[report.id], ["result_ids"]]).then(([read]) => {
        cy.signInAs("administrator");
        callRefused("medilab.test.result", "write", [[read.result_ids[0]], { value: 1 }]).should("eq", "The document has signatures; withdraw them before changing it.");
      }),
    );
  });

  it("TC-F48-02 answers a support request with a reply from sales and tells the customer", () => {
    const reply = "Phiếu kết quả sẽ có trong ngày mai.";
    cy.signInAs("customer");
    cy.visit("/support/new");
    cy.get("input[name=subject]").type(`Hỏi về phiếu kết quả ${Date.now()}`);
    cy.get("textarea[name=body]").type("Khi nào tôi nhận được phiếu kết quả?");
    cy.contains("button", "Send").click();
    cy.location("pathname").should("match", /^\/support\/\d+$/);
    cy.location("pathname").then((path) => {
      const id = Number(path.split("/").pop());
      refAs(ADMIN, "sol_demo.demo_res_partner_hoa").then((hoa) =>
        callAs("demo.sales", "medilab.support.request", "message_post", [[id]], { body: reply, message_type: "comment", subtype_xmlid: "mail.mt_comment" }).then(
          (messageId) => {
            callAs(ADMIN, "medilab.support.request", "read", [[id], ["status"]]).its("0.status").should("eq", "answered");
            callAs(ADMIN, "mail.notification", "search_count", [
              [
                ["mail_message_id", "=", messageId],
                ["res_partner_id", "=", hoa.id],
              ],
            ]).should("eq", 1);
          },
        ),
      );
      cy.reload();
      // The portal shows the conversation inside its own shadow root.
      cy.contains(reply, { includeShadowDom: true }).should("be.visible");
      cy.contains("main p", "Status:").should("contain", "Answered");
    });
  });

  it("TC-F48-03 refuses feedback on an order not completed, and shows no customer another's orders or requests", () => {
    orderAt("submitted").then((order) => {
      cy.signInAs("customer");
      callRefused("sale.order", "action_give_feedback", [[order.id], 5, "Tốt"]).should("eq", "Feedback can be given once the order is completed.");
      refAs(ADMIN, "sol_demo.demo_support_request_open").then(({ id: requestId }) => {
        callAs(ADMIN, "medilab.support.request", "read", [[requestId], ["customer_id"]]).its("0.customer_id.1").should("contain", "Nước Uống Sạch");
        cy.signInAs("individual");
        cy.request({ url: `/orders/${order.id}`, failOnStatusCode: false }).its("status").should("be.oneOf", [403, 404]);
        cy.request({ url: `/support/${requestId}`, failOnStatusCode: false }).its("status").should("be.oneOf", [403, 404]);
      });
    });
  });

  it("TC-F49-01 shows the screens in Vietnamese to a Vietnamese user and in English to an English one", () => {
    cy.signInAs("sales");
    cy.visit("/odoo/my-tasks");
    cy.get(".o_breadcrumb").should("contain", "Nhiệm vụ của tôi");
    cy.signInAs("tester");
    cy.visit("/odoo/my-tasks");
    cy.get(".o_breadcrumb").should("contain", "My Tasks");
  });

  it("TC-F51-01 records who changed a price, when, and its old and new value", () => {
    refAs(ADMIN, "sol_demo.demo_parameter_price_lead").then((price) =>
      refAs(ADMIN, "sol_demo.demo_res_users_administrator").then((administrator) =>
        callAs(ADMIN, "res.users", "read", [[administrator.id], ["name"]]).then(([{ name }]) => {
      cy.signInAs("administrator");
      cy.openRecord(price);
      cy.get("button[name=action_open_audit_history]").click();
      cy.contains(".o_data_row", "Edit").should("contain", name);
      callAs(ADMIN, "medilab.audit.entry", "search_read", [
        [
          ["document_model", "=", "medilab.parameter.price"],
          ["document_id", "=", price.id],
          ["action", "=", "edit"],
        ],
      ], { fields: ["user_id", "create_date", "change_ids"] }).then((entries) => {
        expect(entries[0].user_id[1], "who").to.equal(name);
        expect(entries[0].create_date, "when").to.be.a("string");
        callAs(ADMIN, "medilab.audit.change", "read", [entries.flatMap((entry) => entry.change_ids), ["field_name", "old_value", "new_value"]]).should((changes) =>
          expect(changes.map((change) => [change.field_name, change.old_value, change.new_value])).to.deep.include(["list_price", "250000.0", "280000.0"]),
        );
      });
        }),
      ),
    );
  });

  it("TC-F51-02 includes a request's samples and sample tests in its history, and masks personal data", () => {
    draftReport().then(({ request }) => {
      callAs(ADMIN, "medilab.test.request", "action_open_audit_history", [[request.id]]).then((action) =>
        callAs(ADMIN, "medilab.audit.entry", "search_read", [action.domain], { fields: ["document_model"] }).should((entries) =>
          expect(entries.map((entry) => entry.document_model)).to.include.members(["medilab.test.request", "medilab.sample", "medilab.sample.test"]),
        ),
      );
      cy.signInAs("administrator");
      cy.openRecord(request);
      cy.get("button[name=action_open_audit_history]").click();
      cy.get(".o_data_row").should("have.length.greaterThan", 2);
    });
    const citizenId = `07908${String(Date.now()).slice(-7)}`;
    refAs(ADMIN, "sol_demo.demo_customer_pham_van_long").then((customer) => {
      callAs(ADMIN, "medilab.customer", "read", [[customer.id], ["citizen_id"]]).its("0.citizen_id").as("seeded");
      callAs(ADMIN, "medilab.customer", "write", [[customer.id], { citizen_id: citizenId }]);
      callAs(ADMIN, "medilab.audit.change", "search_read", [
        [
          ["entry_id.document_model", "=", "medilab.customer"],
          ["entry_id.document_id", "=", customer.id],
          ["field_name", "=", "citizen_id"],
        ],
      ], { fields: ["new_value"], order: "id desc", limit: 1 }).its("0.new_value").should("eq", `***${citizenId.slice(-3)}`);
      cy.get("@seeded").then((seeded) => callAs(ADMIN, "medilab.customer", "write", [[customer.id], { citizen_id: seeded }]));
    });
  });

  it("TC-F51-03 lets nobody change or delete an audit entry, administrators included", () => {
    callAs(ADMIN, "medilab.audit.entry", "search", [[]], { limit: 1 }).then(([entry]) => {
      cy.signInAs("administrator");
      callRefused("medilab.audit.entry", "write", [[entry], { note: "Sửa" }]).should("eq", "Audit entries cannot be changed.");
      callRefused("medilab.audit.entry", "unlink", [[entry]]).should("match", /^You are not allowed to delete 'Audit Entry'/);
    });
  });

  it("TC-F52-01 lists every scheduled job with its runs and runs one by hand", () => {
    refAs(ADMIN, "sol_demo.demo_scheduled_job_echo").then((job) => {
      cy.signInAs("administrator");
      cy.visit("/odoo/scheduled-jobs");
      cy.get(".o_list_renderer thead").should("contain", "Next");
      cy.openRecord(job);
      cy.get("button[name=action_run]").click();
      cy.readRecord(job, ["display_name"]).then(({ display_name }) => cy.contains(".o_notification", `${display_name} runs within a minute.`).should("be.visible"));
    });
  });

  it("TC-F52-03 keeps old audit entries in a checked archive file once the cleanup removes them", () => {
    refAs(ADMIN, "sol_demo.demo_archive_file_audit").then((archive) =>
      callAs(ADMIN, "medilab.archive.file", "read", [[archive.id], ["kind", "period_start", "period_end", "row_count", "checksum", "attachment_id"]]).then(([file]) => {
        expect(file.kind).to.equal("audit_entry");
        expect(file.row_count).to.be.greaterThan(0);
        expect(file.checksum).to.match(/^[0-9a-f]{64}$/);
        callAs(ADMIN, "medilab.audit.entry", "search_count", [
          [
            ["create_date", ">=", `${file.period_start} 00:00:00`],
            ["create_date", "<=", `${file.period_end} 23:59:59`],
          ],
        ]).should("eq", 0);
        // The regulation the seeded old notification was about stays.
        refAs(ADMIN, "sol_demo.demo_regulation_qcvn_6_1").then(({ model, id }) => callAs(ADMIN, model, "search_count", [[["id", "=", id]]]).should("eq", 1));
        cy.signInAs("administrator");
        cy.request(`/web/content/${file.attachment_id[0]}?download=true`).its("status").should("eq", 200);
      }),
    );
  });
});

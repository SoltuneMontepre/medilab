import { step } from "../../../support/steps";
import { callAs, callRefused, refAs } from "../../../support/odoo";
import { search } from "../../../support/form";
import { ADMIN, BY_EMAIL, BY_POST, HEAD, LAB_HEAD, PARAMETERS, REISSUED, REPORT, STAFF, assignToTester, draftReport, personNames, reportHtml, testingTasks } from "./setup";

const ACTIONS = ".o_form_view .o_statusbar_buttons";
let stalePartnerForCleanup;
// The report's prepared PDF that waits for signature or was issued.
const signedCandidate = (report) =>
  callAs(
    ADMIN,
    "medilab.test.report.candidate",
    "search_read",
    [
      [
        ["report_id", "=", report.id],
        ["status", "in", ["review", "issued"]],
      ],
    ],
    {
      fields: ["status", "report_number", "attachment_id"],
    },
  ).then((rows) => rows[0]);

// The record's fields as the administrator reads them.
const readAs = (record, fields) => callAs(ADMIN, record.model, "read", [[record.id], fields]).its(0);

// Change a printed business value after preparing the PDF so the stale-candidate case is deterministic.
const makeCandidateStale = (report) =>
  readAs(report, ["request_id"])
    .then(({ request_id }) => callAs(ADMIN, "medilab.test.request", "read", [[request_id[0]], ["customer_id"]]))
    .then(([request]) => callAs(ADMIN, "medilab.customer", "read", [[request.customer_id[0]], ["partner_id"]]))
    .then(([customer]) => {
      const partnerId = customer.partner_id[0];
      return callAs(ADMIN, "res.partner", "read", [[partnerId], ["name"]]).then(([partner]) => {
        stalePartnerForCleanup = { id: partnerId, name: partner.name };
        return callAs(ADMIN, "res.partner", "write", [[partnerId], { name: "Changed after PDF preparation" }]);
      });
    });

// The base64 content of a file the browser's session downloads.
const downloaded = (url) => cy.request({ url, encoding: "base64" }).its("body");

// The message raised for a report, by its event: `issued` tells the customer, `delivered` e-mails the PDF. With
// `partnerId`, only a message that notifies that partner.
const reportMessage = (report, event, partnerId) =>
  callAs(
    ADMIN,
    "mail.message",
    "search_read",
    [[["notification_key", "=", `test_report:${report.id}:${event}`], ...(partnerId ? [["notification_ids.res_partner_id", "=", partnerId]] : [])]],
    { fields: ["subject", "attachment_ids"] },
  );

// The rows of a list of the Laboratory menu, by its path.
function listRows(path) {
  cy.visit(`/odoo/${path}`);
  return cy.get(".o_list_view").should("be.visible").find(".o_data_row, .o_view_nocontent").should("exist");
}

// The replacement of a report, made through a change request the lab head approves when it has none yet.
function replacementOf(report) {
  const replacements = () => callAs(ADMIN, REPORT, "search_read", [[["replaces_id", "=", report.id]]], { fields: ["status"] });
  return replacements().then((rows) => {
    if (rows.length) return rows[0];
    return callAs(STAFF, "medilab.change.request.raise", "create", [
      {
        document_model: REPORT,
        document_id: report.id,
        requested_change: "Phát hành lại phiếu với địa chỉ nhận mới của khách hàng.",
        reason: "Khách hàng đã đổi địa chỉ nhận phiếu.",
      },
    ]).then((wizard) =>
      callAs(STAFF, "medilab.change.request.raise", "action_raise", [[wizard]]).then((action) => {
        cy.signInAs("lab_head");
        cy.openRecord({ model: "medilab.change.request", id: action.res_id });
        cy.signRecord();
        cy.get(".modal-footer .btn-primary").click();
        cy.get(`${ACTIONS} button[name=action_open_new_version]`).should("be.visible");
        return replacements().then((rows) => rows[0]);
      }),
    );
  });
}

// Sample delivery staff record the delivery of an issued report from the reports waiting for delivery.
function deliverFromList(code) {
  cy.signInAs("sample_delivery_staff");
  cy.visit("/odoo/reports-to-deliver");
  search(code);
  cy.contains(".o_data_row", code).find("button[name=action_record_delivery]").click();
  cy.contains(".o_data_row", code).should("not.exist");
}

// The head of department gives the result sent back to the tester, who signs it again, and approves it, as in WF-04.
function approveAgain(result) {
  testingTasks([result.sample_test_id[0]]).then(assignToTester);
  callAs("demo.tester", "medilab.test.result", "action_sign", [[result.id]]);
  callAs(HEAD, "medilab.test.result", "action_sign", [[result.id]]);
}

describe("WF-06 Report release", () => {
  afterEach(() => {
    if (!stalePartnerForCleanup) return;
    const { id, name } = stalePartnerForCleanup;
    stalePartnerForCleanup = undefined;
    return callAs(ADMIN, "res.partner", "write", [[id], { name }]);
  });
  it("TC-WF06-M issues the report with its number, delivers it by e-mail and lets the customer download it", () => {
    refAs(ADMIN, "sol_demo.demo_res_partner_nuoc_sach").then((customer) =>
      refAs(ADMIN, "sol_demo.demo_res_partner_hoa").then((hoa) =>
        refAs(ADMIN, BY_EMAIL).then((report) =>
          readAs(report, ["status", "code", "attachment_id", "request_id", "delivered_by_id", "withheld_for_payment"]).then((issued) => {
            step("The issued report has its number and PDF, and its test request is reported");
            expect(issued.status).to.equal("issued");
            expect(issued.code).to.match(/^PKQ\.\d{4}\.\d+$/);
            expect(issued.attachment_id[1]).to.equal(`${issued.code}.pdf`);
            expect(issued.withheld_for_payment).to.equal(false);
            readAs({ model: "medilab.test.request", id: issued.request_id[0] }, ["status"]).its("status").should("eq", "reported");
            callAs(ADMIN, "sale.order", "search_read", [[["test_request_id", "=", issued.request_id[0]]]], {
              fields: ["amount_total", "payment_status"],
            }).should(([order]) => {
              expect(order.amount_total).to.be.greaterThan(0);
              expect(order.payment_status).to.equal("paid");
            });
            step("The customer is told of the issue, and staff deliver the PDF by e-mail");
            reportMessage(report, "issued", customer.id).its("0.subject").should("eq", issued.code);
            personNames("sol_demo.demo_person_sample_delivery_staff").then(([staff]) => expect(issued.delivered_by_id[1]).to.equal(staff));
            reportMessage(report, "delivered", hoa.id).should(([message]) => {
              expect(message, "e-mail to the recipient").to.exist;
              expect(message.attachment_ids, "PDF").to.include(issued.attachment_id[0]);
            });

            step("The customer opens Test reports on the portal and downloads the report");
            cy.signInAs("customer");
            cy.intercept("POST", "/my/counters", (request) => {
              if (request.body.params?.counters?.test_report_count) {
                request.alias = "portalTestReportCounters";
              }
            });
            cy.visit("/my");
            cy.wait("@portalTestReportCounters").then(({ response }) => {
              expect(response.statusCode).to.equal(200);
              expect(response.body.result.test_report_count).to.equal(1);
            });
            cy.get("main a[href='/my/test-reports']").first().should("be.visible").click();
            cy.contains("main", issued.code).should("be.visible");
            cy.request(`/my/test-reports/${report.id}/download`).its("headers.content-type").should("contain", "application/pdf");
          }),
        ),
      ),
    );
  });

  it("TC-WF06-A1 records a delivery in person or by post without sending an e-mail", () => {
    // Each demo report is delivered once; a later run on the same database finds it delivered.
    step("Sample delivery staff record the delivery of a report sent by post");
    refAs(ADMIN, BY_POST).then((report) =>
      readAs(report, ["code", "delivery_method", "delivered_at", "withheld_for_payment"]).then((read) => {
        expect(read.delivery_method).to.equal("post");
        expect(read.withheld_for_payment).to.equal(false);
        if (!read.delivered_at) deliverFromList(read.code);
      }),
    );
    step("Staff record the delivery of a report handed over in person");
    refAs(ADMIN, REISSUED).then((report) =>
      readAs(report, ["delivery_method", "delivered_at", "withheld_for_payment"]).then((read) => {
        expect(read.delivery_method).to.equal("in_person");
        expect(read.withheld_for_payment).to.equal(false);
        if (read.delivered_at) return;
        cy.signInAs("sample_delivery_staff");
        cy.openRecord(report);
        cy.get(`${ACTIONS} button[name=action_record_delivery]`).click();
        cy.get(`${ACTIONS} button[name=action_record_delivery]`).should("not.exist");
      }),
    );
    step("Both are delivered, and neither sent an e-mail");
    for (const xmlId of [BY_POST, REISSUED]) {
      refAs(ADMIN, xmlId).then((report) => {
        readAs(report, ["delivered_at"]).its("delivered_at").should("be.a", "string");
        reportMessage(report, "delivered").should("be.empty");
      });
    }
  });

  it("TC-WF06-A2 issues the report in English, Vietnamese or both, as the request asks", () => {
    const headings = { en: "Test Report", vi: "Phiếu Kết Quả" };
    step("The lab head reads reports issued in English, in Vietnamese and in both");
    cy.signInAs("lab_head");
    for (const [xmlId, language] of [
      [BY_EMAIL, "en"],
      [BY_POST, "vi"],
      [REISSUED, "bilingual"],
    ]) {
      refAs(ADMIN, xmlId).then((report) => {
        readAs(report, ["language"]).its("language").should("eq", language);
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

  it("TC-WF06-A3 leaves a cancelled test off the report", () => {
    draftReport({ cancel: [PARAMETERS.ph] }).then(({ report }) => {
      step("The draft report of a request with a cancelled test holds one result");
      callAs(LAB_HEAD, REPORT, "read", [[report.id], ["result_ids"]])
        .its("0.result_ids.length")
        .should("eq", 1);
      step("The lab head's report shows Lead (Pb) and leaves out the cancelled pH");
      cy.signInAs("lab_head");
      reportHtml(report).should((html) => {
        expect(html).to.contain("Lead (Pb)");
        expect(html).not.to.match(/>\s*pH\s*</);
      });
    });
  });

  it("TC-WF06-E1 keeps a report with an out-of-date PDF pending digital signing", () => {
    refAs(ADMIN, "sol_demo.demo_test_report_pending").then((report) =>
      signedCandidate(report)
        .then((candidate) => makeCandidateStale(report).then(() => candidate))
        .then((candidate) =>
          readAs(report, ["status", "code", "attachment_id", "request_id", "candidate_current"]).then((read) => ({
            candidate,
            read,
          })),
        )
        .then(({ candidate, read }) => {
          expect(read.status).to.equal("pending_signing");
          expect(read.code).to.equal(candidate.report_number);
          expect(read.attachment_id).to.equal(false);
          expect(read.candidate_current).to.equal(false);

          step("A report waiting for its digital signature cannot be delivered");
          cy.signInAs("sample_delivery_staff");
          listRows("reports-to-deliver").should("not.contain.text", read.code);
          callRefused(REPORT, "action_record_delivery", [[report.id]]).should("be.a", "string");
          step("The customer cannot download it");
          cy.signInAs("customer");
          cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false })
            .its("status")
            .should("eq", 404);

          step("The lab head retries the digital signing, which issues the reviewed PDF");
          cy.signInAs("lab_head");
          listRows("reports-to-sign").should("not.contain.text", read.request_id[1]);
          cy.openRecord(report);
          cy.get(".o_form_view .alert-warning").should("contain.text", "prepared PDF no longer matches");
          cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
          cy.get(`${ACTIONS} button[name=action_retry_digital_signing]`).should("not.exist");
          callRefused(REPORT, "action_retry_digital_signing", [[report.id]]).should("contain", "no longer matches its sources");
          step("A stale candidate cannot issue the report");
          return readAs(report, ["status", "code", "attachment_id"]).should((final) => {
            expect(final.status).to.equal("pending_signing");
            expect(final.code).to.equal(candidate.report_number);
            expect(final.attachment_id).to.equal(false);
          });
        }),
    );
  });

  it("TC-WF06-E1 keeps the issued report current until its replacement is issued", () => {
    step("An issued replacement marks the report it replaces as replaced");
    refAs(ADMIN, "sol_demo.demo_test_report_in_person").then((replaced) =>
      refAs(ADMIN, "sol_demo.demo_test_report_reissued").then((reissued) => {
        readAs(replaced, ["status"]).its("status").should("eq", "replaced");
        readAs(reissued, ["status", "replaces_id"]).should((read) => {
          expect(read.status).to.equal("issued");
          expect(read.replaces_id[0]).to.equal(replaced.id);
        });
      }),
    );
    step("A change request makes a draft replacement of an issued report");
    refAs(ADMIN, "sol_demo.demo_test_report_by_email").then((report) =>
      replacementOf(report).then((replacement) => {
        expect(replacement.status).to.equal("draft");
        readAs(report, ["status", "request_id"]).then((read) => {
          expect(read.status).to.equal("issued");
          cy.signInAs("lab_head");
          listRows("reports-to-sign").should("contain.text", read.request_id[1]);
        });
        // The replacement waits for its own prepared PDF before the lab head can sign it.
        step("The replacement waits for its own PDF before the lab head signs it");
        callAs(LAB_HEAD, REPORT, "read", [[replacement.id], ["approval_can_sign"]])
          .its("0.approval_can_sign")
          .should("eq", false);
        step("The customer still downloads the issued report, not the draft replacement");
        cy.signInAs("customer");
        cy.request(`/my/test-reports/${report.id}/download`).its("headers.content-type").should("contain", "application/pdf");
        cy.request({ url: `/my/test-reports/${replacement.id}/download`, failOnStatusCode: false })
          .its("status")
          .should("eq", 404);
      }),
    );
  });

  it("TC-WF06-E2 sends the named results back to their department, and gives the lab head a new signing task once they are approved again", () => {
    const reason = "Lead reads above last month's blank; check the digestion blank and measure again.";
    draftReport().then(({ request, report }) => {
      step("The lab head rejects the report, naming the lead result and a reason");
      cy.signInAs("lab_head");
      cy.openRecord(report);
      cy.contains(`${ACTIONS} button`, "Reject").click();
      cy.get(".modal .o_field_widget[name=reason] textarea").type(reason);
      cy.get(".modal .o_field_widget[name=result_ids] input").type("Lead");
      cy.contains(".o-autocomplete--dropdown-item a", "Lead (Pb)").click();
      cy.get(".modal button[name=action_reject]").click();
      cy.get(".modal").should("not.exist");
      step("The lead result goes back to its department with a new testing task");
      cy.readRecord(report, ["status", "result_ids"]).then((read) => {
        expect(read.status).to.equal("draft");
        callAs(HEAD, "medilab.test.result", "read", [read.result_ids, ["parameter_id", "status", "sample_test_id"]]).then((results) => {
          const lead = results.find((result) => result.parameter_id[1] === "Lead (Pb)");
          expect(lead.status, "lead result").to.equal("none");
          callAs(
            HEAD,
            "medilab.task",
            "search_read",
            [
              [
                ["document_model", "=", "medilab.sample.test"],
                ["document_id", "=", lead.sample_test_id[0]],
                ["status", "=", "open"],
              ],
            ],
            { fields: ["name", "note", "assignee_id"] },
          ).then(([task]) => {
            expect(task.assignee_id, "unassigned").to.equal(false);
            expect(task.note).to.contain(reason);
            cy.signInAs("head_of_department");
            cy.visit("/odoo/department-queue");
            cy.contains(".o_searchview_facet", "Department").find(".o_facet_remove").click();
            search(task.name);
            cy.contains(".o_data_row", task.name).should("be.visible");
            step("The department tests it again and approves it");
            approveAgain(lead);
          });
        });
      });
      step("The lab head has a new signing task");
      callAs(LAB_HEAD, "medilab.test.request", "read", [[request.id], ["status"]])
        .its("0.status")
        .should("eq", "completed");
      callAs(
        LAB_HEAD,
        "medilab.task",
        "search_read",
        [
          [
            ["document_model", "=", REPORT],
            ["document_id", "=", report.id],
            ["status", "=", "open"],
          ],
        ],
        { fields: ["name"] },
      ).should("have.length", 1);
    });
  });
});

describe("WF-06 feature acceptance criteria", () => {
  it("TC-F43-02 prints the approving heads and the lab head, never the testers", () => {
    personNames("sol_demo.demo_person_head_of_department", "sol_demo.demo_person_lab_head", "sol_demo.demo_person_tester").then(
      ([head, labHead, tester]) => {
        cy.signInAs("lab_head");
        refAs(ADMIN, BY_EMAIL).then((report) =>
          reportHtml(report).should((html) => {
            expect(html).to.contain(head).and.contain(labHead);
            expect(html).not.to.contain(tester);
          }),
        );
      },
    );
  });

  it("TC-F43-03 refuses to reject a report without a reason or without naming a result", () => {
    draftReport().then(({ report }) => {
      cy.signInAs("lab_head");
      cy.openRecord(report);
      cy.contains(`${ACTIONS} button`, "Reject").click();
      cy.get(".modal .o_field_widget[name=reason] textarea").type("The blank is too high.");
      cy.expectRefusal({
        read: () => cy.readRecord(report, ["status", "write_date"]),
        action: () => cy.get(".modal button[name=action_reject]").click(),
        message: "Name the results to check again.",
      });
      cy.readRecord(report, ["result_ids"]).then(({ result_ids }) =>
        callRefused(REPORT, "action_reject", [[report.id], "", result_ids]).should("eq", "A rejection needs a reason."),
      );
    });
  });

  it("TC-F45-03 refuses to deliver an unissued report, and lets a customer download only their own reports", () => {
    draftReport().then(({ report }) => {
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(report);
      cy.get(`${ACTIONS} button[name=action_record_delivery]`).should("not.exist");
      callRefused(REPORT, "action_record_delivery", [[report.id]]).should("contain", "Only an issued report");
      readAs(report, ["status", "delivered_at"]).should((read) => {
        expect(read.status).to.equal("draft");
        expect(read.delivered_at).to.equal(false);
      });
      cy.signInAs("customer");
      cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false })
        .its("status")
        .should("eq", 404);
    });
    refAs(ADMIN, BY_EMAIL).then((report) => {
      cy.signInAs("individual");
      cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false })
        .its("status")
        .should("eq", 404);
      readAs(report, ["status", "attachment_id", "request_id"]).then((issued) => {
        expect(issued.status).to.equal("issued");
        expect(issued.attachment_id[0]).to.be.a("number");
        return readAs({ model: "medilab.test.request", id: issued.request_id[0] }, ["customer_id"]).then(
          (request) =>
            refAs(ADMIN, "sol_demo.demo_customer_nuoc_sach").then((customer) => {
              expect(request.customer_id[0]).to.equal(customer.id);
              cy.signInAs("customer");
              cy.request(`/my/test-reports/${report.id}/download`).its("status").should("eq", 200);
            }),
        );
      });
      cy.signInAs("individual");
      cy.intercept("POST", "/my/counters", (request) => {
        if (request.body.params?.counters?.test_report_count) {
          request.alias = "portalTestReportCounters";
        }
      });
      cy.visit("/my");
      cy.wait("@portalTestReportCounters").then(({ response }) => {
        expect(response.statusCode).to.equal(200);
        expect(response.body.result.test_report_count).to.equal(0);
      });
      cy.get("main a[href='/my/test-reports']").should("not.be.visible");
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

});

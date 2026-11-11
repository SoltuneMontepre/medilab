import { callAs, callRefused, refAs } from "../../../support/odoo";
import { search } from "../../../support/form";
import { HEAD, LAB_HEAD, PARAMETERS, STAFF, assignToTester, draftReport, testingTasks } from "./setup";

const ADMIN = "demo.administrator";
const REPORT = "medilab.test.report";
const ACTIONS = ".o_form_view .o_statusbar_buttons";
// The demo's issued reports: in English and delivered by e-mail, in Vietnamese and digitally signed for delivery by
// post, and bilingual as the replacement of a report delivered in person. A new report is never issued in the browser
// tests, as its PDF is prepared through ONLYOFFICE.
const BY_EMAIL = "sol_demo.demo_test_report_by_email";
const BY_POST = "sol_demo.demo_test_report_by_post";
const REISSUED = "sol_demo.demo_test_report_reissued";

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

// The body of the rendered report, as the signed-in user prints it.
const reportHtml = (report) => cy.request(`/report/html/sol_laboratory.report_test_report/${report.id}`).then(({ body }) => body.split("<main")[1]);

// Demo people's names, in the order of their external IDs.
const personNames = (...xmlIds) =>
  callAs(
    ADMIN,
    "ir.model.data",
    "search_read",
    [
      [
        ["module", "=", "sol_demo"],
        ["name", "in", xmlIds.map((xmlId) => xmlId.split(".")[1])],
      ],
    ],
    {
      fields: ["name", "res_id"],
    },
  ).then((rows) =>
    callAs(ADMIN, "medilab.person", "read", [xmlIds.map((xmlId) => rows.find((row) => `sol_demo.${row.name}` === xmlId).res_id), ["name"]]).then(
      (people) => people.map((person) => person.name),
    ),
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
  it("TC-WF06-M issues the report with its number, delivers it by e-mail and lets the customer download it", () => {
    refAs(ADMIN, "sol_demo.demo_res_partner_nuoc_sach").then((customer) =>
      refAs(ADMIN, "sol_demo.demo_res_partner_hoa").then((hoa) =>
        refAs(ADMIN, BY_EMAIL).then((report) =>
          readAs(report, ["status", "code", "attachment_id", "request_id", "delivered_by_id"]).then((issued) => {
            expect(issued.status).to.equal("issued");
            expect(issued.code).to.match(/^PKQ\.\d{4}\.\d+$/);
            expect(issued.attachment_id[1]).to.equal(`${issued.code}.pdf`);
            readAs({ model: "medilab.test.request", id: issued.request_id[0] }, ["status"]).its("status").should("eq", "reported");
            reportMessage(report, "issued", customer.id).its("0.subject").should("eq", issued.code);
            personNames("sol_demo.demo_person_sample_delivery_staff").then(([staff]) => expect(issued.delivered_by_id[1]).to.equal(staff));
            reportMessage(report, "delivered", hoa.id).should(([message]) => {
              expect(message, "e-mail to the recipient").to.exist;
              expect(message.attachment_ids, "PDF").to.include(issued.attachment_id[0]);
            });

            cy.signInAs("customer");
            cy.visit("/my/test-reports");
            cy.contains("main", issued.code).should("be.visible");
            cy.request(`/my/test-reports/${report.id}/download`).its("headers.content-type").should("contain", "application/pdf");
          }),
        ),
      ),
    );
  });

  it("TC-WF06-A1 records a delivery in person or by post without sending an e-mail", () => {
    // Each demo report is delivered once; a later run on the same database finds it delivered.
    refAs(ADMIN, BY_POST).then((report) =>
      readAs(report, ["code", "delivery_method", "delivered_at"]).then((read) => {
        expect(read.delivery_method).to.equal("post");
        if (!read.delivered_at) deliverFromList(read.code);
      }),
    );
    refAs(ADMIN, REISSUED).then((report) =>
      readAs(report, ["delivery_method", "delivered_at"]).then((read) => {
        expect(read.delivery_method).to.equal("in_person");
        if (read.delivered_at) return;
        cy.signInAs("sample_delivery_staff");
        cy.openRecord(report);
        cy.get(`${ACTIONS} button[name=action_record_delivery]`).click();
        cy.get(`${ACTIONS} button[name=action_record_delivery]`).should("not.exist");
      }),
    );
    for (const xmlId of [BY_POST, REISSUED]) {
      refAs(ADMIN, xmlId).then((report) => {
        readAs(report, ["delivered_at"]).its("delivered_at").should("be.a", "string");
        reportMessage(report, "delivered").should("be.empty");
      });
    }
  });

  it("TC-WF06-A2 issues the report in English, Vietnamese or both, as the request asks", () => {
    const headings = { en: "Test Report", vi: "Phiếu Kết Quả" };
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
      callAs(LAB_HEAD, REPORT, "read", [[report.id], ["result_ids"]])
        .its("0.result_ids.length")
        .should("eq", 1);
      cy.signInAs("lab_head");
      reportHtml(report).should((html) => {
        expect(html).to.contain("Lead (Pb)");
        expect(html).not.to.match(/>\s*pH\s*</);
      });
    });
  });

  it("TC-WF06-E1 keeps a report pending digital signing unissued, then issues its reviewed PDF once on retry", () => {
    refAs(ADMIN, "sol_demo.demo_test_report_pending").then((report) =>
      signedCandidate(report).then((candidate) => {
        readAs(report, ["status", "code", "attachment_id", "request_id"]).then((read) => {
          expect(read.status).to.equal("pending_signing");
          expect(read.code).to.equal(candidate.report_number);
          expect(read.attachment_id).to.equal(false);

          cy.signInAs("sample_delivery_staff");
          listRows("reports-to-deliver").should("not.contain.text", read.code);
          callRefused(REPORT, "action_record_delivery", [[report.id]]).should("be.a", "string");
          cy.signInAs("customer");
          cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false })
            .its("status")
            .should("eq", 404);

          cy.signInAs("lab_head");
          listRows("reports-to-sign").should("not.contain.text", read.request_id[1]);
          cy.openRecord(report);
          cy.get(".o_form_view .alert-warning").should("contain.text", "Viettel Sign");
          cy.get(`${ACTIONS} button[name=action_sign]`).should("not.exist");
          // Digital signing is off in the demo, so the retry issues the reviewed PDF as it is.
          cy.get(`${ACTIONS} button[name=action_retry_digital_signing]`).click();
          cy.get(`${ACTIONS} button[name=action_retry_digital_signing]`).should("not.exist");
          cy.get(`${ACTIONS} button[name=action_download]`).should("be.visible");
        });
        readAs(report, ["status", "code"]).should((read) => {
          expect(read.status).to.equal("issued");
          expect(read.code).to.equal(candidate.report_number);
        });
        signedCandidate(report).its("status").should("eq", "issued");
        callRefused(REPORT, "action_retry_digital_signing", [[report.id]]).should("be.a", "string");
        downloaded(`/web/content/${candidate.attachment_id[0]}`).then((reviewed) => {
          cy.signInAs("customer");
          downloaded(`/my/test-reports/${report.id}/download`).should("eq", reviewed);
        });
      }),
    );
  });

  it("TC-WF06-E1 keeps the issued report current until its replacement is issued", () => {
    refAs(ADMIN, "sol_demo.demo_test_report_in_person").then((replaced) =>
      refAs(ADMIN, "sol_demo.demo_test_report_reissued").then((reissued) => {
        readAs(replaced, ["status"]).its("status").should("eq", "replaced");
        readAs(reissued, ["status", "replaces_id"]).should((read) => {
          expect(read.status).to.equal("issued");
          expect(read.replaces_id[0]).to.equal(replaced.id);
        });
      }),
    );
    refAs(ADMIN, "sol_demo.demo_test_report_by_email").then((report) =>
      replacementOf(report).then((replacement) => {
        expect(replacement.status).to.equal("draft");
        readAs(report, ["status", "request_id"]).then((read) => {
          expect(read.status).to.equal("issued");
          cy.signInAs("lab_head");
          listRows("reports-to-sign").should("contain.text", read.request_id[1]);
        });
        // The replacement waits for its own prepared PDF before the lab head can sign it.
        callAs(LAB_HEAD, REPORT, "read", [[replacement.id], ["approval_can_sign"]])
          .its("0.approval_can_sign")
          .should("eq", false);
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
      cy.signInAs("lab_head");
      cy.openRecord(report);
      cy.contains(`${ACTIONS} button`, "Reject").click();
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
            approveAgain(lead);
          });
        });
      });
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

// A new accreditation certificate valid until `validUntil`.
function newCertificate(validUntil = "2099-12-31") {
  return callAs(ADMIN, "medilab.accreditation.certificate", "create", [
    { code: `VILAS-E2E-${Date.now()}`, issuing_body: "BoA", valid_until: validUntil },
  ]).then((id) => ({ model: "medilab.accreditation.certificate", id }));
}

describe("WF-06 feature acceptance criteria", () => {
  it("TC-F41-01 imports 30 scope lines, creating only the missing methods and keeping the titles of existing ones", () => {
    const stamp = Date.now();
    newCertificate().then((certificate) =>
      refAs(ADMIN, "sol_demo.demo_testing_field_chemistry").then((field) =>
        refAs(ADMIN, "sol_demo.demo_testing_method_tcvn_7602").then((first) =>
          refAs(ADMIN, "sol_demo.demo_testing_method_tcvn_6187_1").then((second) =>
            refAs(ADMIN, PARAMETERS.lead).then((lead) =>
              refAs(ADMIN, "sol_demo.demo_sample_type_bottled_water").then((water) =>
                callAs(
                  ADMIN,
                  "medilab.testing.method",
                  "read",
                  [
                    [first.id, second.id],
                    ["code", "name"],
                  ],
                  { context: { lang: "vi_VN" } },
                ).then((known) => {
                  const scope = { parameter_ids: [[6, 0, [lead.id]]], sample_type_ids: [[6, 0, [water.id]]] };
                  // Two methods the laboratory already has, under other titles that must not replace theirs.
                  const lines = [
                    ...known.map((method) => ({ code: method.code, name: `Tên khác của ${method.code}` })),
                    ...Array.from({ length: 28 }, (_, index) => ({ code: `E2E-${stamp}-${index + 1}`, name: `Phương pháp nhập ${index + 1}` })),
                  ];
                  callAs(ADMIN, "medilab.accreditation.certificate.import", "create", [
                    {
                      certificate_id: certificate.id,
                      field_id: field.id,
                      lang: "vi_VN",
                      line_ids: lines.map((line) => [0, 0, { ...line, ...scope }]),
                    },
                  ]).then((wizard) => callAs(ADMIN, "medilab.accreditation.certificate.import", "action_import", [[wizard]]));
                  callAs(ADMIN, "medilab.testing.method", "read", [[first.id, second.id], ["name"]], { context: { lang: "vi_VN" } }).should((after) =>
                    expect(after.map((method) => method.name)).to.deep.equal(known.map((method) => method.name)),
                  );
                  callAs(ADMIN, "medilab.testing.method", "search_count", [[["code", "=like", `E2E-${stamp}-%`]]]).should("eq", 28);
                  cy.signInAs("administrator");
                  cy.openRecord(certificate);
                  cy.get(".o_field_widget[name=scope_line_ids] .o_data_row").should("have.length", 30);
                }),
              ),
            ),
          ),
        ),
      ),
    );
  });

  it("TC-F42-01 prints the mark of a valid quality registration after the parameter it covers", () => {
    cy.signInAs("lab_head");
    refAs(ADMIN, BY_EMAIL).then((report) => reportHtml(report).should("match", /Lead \(Pb\)\s*\(\*\)/));
  });

  it("TC-F42-03 prints no mark of a quality registration past its last valid day", () => {
    refAs(ADMIN, "sol_demo.demo_quality_registration_expired").then((registration) =>
      callAs(ADMIN, "medilab.quality.registration", "read", [[registration.id], ["valid_until", "report_mark"]]).then(([expired]) => {
        expect(new Date(expired.valid_until), "last valid day").to.be.below(new Date());
        cy.signInAs("lab_head");
        // The expired registration covers pH.
        refAs(ADMIN, BY_EMAIL).then((report) =>
          reportHtml(report).should((html) => {
            expect(html).to.contain("pH");
            expect(html).not.to.contain(expired.report_mark);
          }),
        );
      }),
    );
  });

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

  it("TC-F44-01 shows who holds the lock of a document another user is editing, and still lets others read it", () => {
    draftReport().then(({ request }) => {
      callAs(STAFF, "medilab.test.request", "lock_take", [[request.id]])
        .its("taken")
        .should("eq", true);
      cy.signInAs("administrator");
      cy.openRecord(request);
      personNames("sol_demo.demo_person_sample_delivery_staff").then(([staff]) => cy.contains(".o_form_view", "is editing").should("contain", staff));
      cy.get(".o_field_widget[name=customer_id] input").invoke("val").should("contain", "Nước Uống Sạch");
      callAs(STAFF, "medilab.test.request", "lock_release", [[request.id], "left"]);
    });
  });

  it("TC-F44-03 keeps a signed document read-only for everyone, administrators included", () => {
    draftReport().then(({ report }) =>
      callAs(LAB_HEAD, REPORT, "read", [[report.id], ["result_ids"]]).then(([read]) => {
        cy.signInAs("administrator");
        callRefused("medilab.test.result", "write", [[read.result_ids[0]], { value: 1 }]).should(
          "eq",
          "The document has signatures; withdraw them before changing it.",
        );
      }),
    );
  });

  it("TC-F45-03 refuses to deliver an unissued report, and lets a customer download only their own reports", () => {
    draftReport().then(({ report }) => {
      cy.signInAs("sample_delivery_staff");
      cy.openRecord(report);
      cy.get(`${ACTIONS} button[name=action_record_delivery]`).should("not.exist");
      callRefused(REPORT, "action_record_delivery", [[report.id]]).should("match", /^Only an issued report not delivered yet can be delivered: /);
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
      cy.signInAs("customer");
      cy.request(`/my/test-reports/${report.id}/download`).its("status").should("eq", 200);
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
          callAs(
            ADMIN,
            "medilab.audit.entry",
            "search_read",
            [
              [
                ["document_model", "=", "medilab.parameter.price"],
                ["document_id", "=", price.id],
                ["action", "=", "edit"],
              ],
            ],
            { fields: ["user_id", "create_date", "change_ids"] },
          ).then((entries) => {
            expect(entries[0].user_id[1], "who").to.equal(name);
            expect(entries[0].create_date, "when").to.be.a("string");
            callAs(ADMIN, "medilab.audit.change", "read", [
              entries.flatMap((entry) => entry.change_ids),
              ["field_name", "old_value", "new_value"],
            ]).should((changes) =>
              expect(changes.map((change) => [change.field_name, change.old_value, change.new_value])).to.deep.include([
                "list_price",
                "250000.0",
                "280000.0",
              ]),
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
      callAs(ADMIN, "medilab.customer", "read", [[customer.id], ["citizen_id"]])
        .its("0.citizen_id")
        .as("seeded");
      callAs(ADMIN, "medilab.customer", "write", [[customer.id], { citizen_id: citizenId }]);
      callAs(
        ADMIN,
        "medilab.audit.change",
        "search_read",
        [
          [
            ["entry_id.document_model", "=", "medilab.customer"],
            ["entry_id.document_id", "=", customer.id],
            ["field_name", "=", "citizen_id"],
          ],
        ],
        { fields: ["new_value"], order: "id desc", limit: 1 },
      )
        .its("0.new_value")
        .should("eq", `***${citizenId.slice(-3)}`);
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
      cy.readRecord(job, ["display_name"]).then(({ display_name }) =>
        cy.contains(".o_notification", `${display_name} runs within a minute.`).should("be.visible"),
      );
    });
  });

  it("TC-F52-03 keeps old audit entries in a checked archive file once the cleanup removes them", () => {
    refAs(ADMIN, "sol_demo.demo_archive_file_audit").then((archive) =>
      callAs(ADMIN, "medilab.archive.file", "read", [
        [archive.id],
        ["kind", "period_start", "period_end", "row_count", "checksum", "attachment_id"],
      ]).then(([file]) => {
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
        refAs(ADMIN, "sol_demo.demo_regulation_qcvn_6_1").then(({ model, id }) =>
          callAs(ADMIN, model, "search_count", [[["id", "=", id]]]).should("eq", 1),
        );
        cy.signInAs("administrator");
        cy.request(`/web/content/${file.attachment_id[0]}?download=true`).its("status").should("eq", 200);
      }),
    );
  });
});

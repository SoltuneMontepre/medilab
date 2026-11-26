import { pick, save } from "../../../support/form";
import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { step } from "../../../support/steps";
import {
  ADMINISTRATOR,
  EXPIRED_SUBCONTRACTOR,
  archivedSubcontractor,
  inDays,
  newParameter,
  newSubcontractor,
  shownDate,
  wayParts,
} from "../wf-05-outsourced-testing/setup";
import { ADMIN, BY_EMAIL, PARAMETERS, reportHtml } from "../wf-06-report-release/setup";

// A new accreditation certificate valid until `validUntil`.
function newCertificate(validUntil = "2099-12-31") {
  return callAs(ADMIN, "medilab.accreditation.certificate", "create", [
    { code: `VILAS-E2E-${Date.now()}`, issuing_body: "BoA", valid_until: validUntil },
  ]).then((id) => ({ model: "medilab.accreditation.certificate", id }));
}

describe("SF-06 subcontractors, accreditation and registrations (F-37, F-41, F-42)", () => {
  it("TC-F37-01 lets the administrator choose a subcontractor with a valid accreditation on a way of testing", () => {
    newParameter().then((parameter) => {
      cy.signInAs("administrator");
      cy.openRecord(parameter);
      cy.get(".o_field_widget[name=method_ids] .o_field_x2many_list_row_add button").click();
      pick("method_id", "ISO 17294-2");
      // With nothing typed, the suggestions start from the first subcontractor codes, the seeded ones.
      cy.get(".o_selected_row .o_field_widget[name=subcontractor_id] input").click();
      cy.get(".o-autocomplete--dropdown-menu").should("contain", "Northern").and("not.contain", "Coastal").and("not.contain", "Mekong");
      cy.contains(".o-autocomplete--dropdown-item a", "Northern").click();
      save();
      call("medilab.parameter.method", "search_read", [[["parameter_id", "=", parameter.id]]], { fields: ["subcontractor_id"] }).should(([way]) =>
        expect(way.subcontractor_id[1]).to.contain("Northern"),
      );
    });
  });

  it("TC-F37-02 keeps a way's subcontractor after its accreditation expires, and renewing it makes it selectable again", () => {
    wayParts().then(({ methodId }) =>
      newSubcontractor().then((subcontractor) =>
        newParameter().then((first) =>
          newParameter().then((second) => {
            const way = (parameter) => ({ parameter_id: parameter.id, method_id: methodId, subcontractor_id: subcontractor.id });
            callAs(ADMINISTRATOR, "medilab.parameter.method", "create", [way(first)]).then((id) => {
              const kept = { model: "medilab.parameter.method", id };
              callAs(ADMINISTRATOR, "medilab.subcontractor", "write", [[subcontractor.id], { accreditation_expiry: inDays(-1) }]);
              cy.signInAs("administrator");
              call(kept.model, "write", [[id], { allows_negative: true }]);
              cy.readRecord(kept, ["subcontractor_id", "allows_negative"]).should((read) => {
                expect(read.subcontractor_id[0]).to.equal(subcontractor.id);
                expect(read.allows_negative).to.equal(true);
              });
              callRefused(kept.model, "create", [way(second)]).should(
                "match",
                new RegExp(`^The accreditation of ${subcontractor.name} expired on .+\\. Renew it before choosing this subcontractor\\.$`),
              );
              cy.openRecord(subcontractor);
              cy.get(".o_field_widget[name=accreditation_expiry] button").click();
              cy.get(".o_field_widget[name=accreditation_expiry] input")
                .clear()
                .type(shownDate(inDays(365)));
              save();
              call(kept.model, "create", [way(second)]).should("be.a", "number");
            });
          }),
        ),
      ),
    );
  });

  it("TC-F37-03 refuses to choose an archived subcontractor, or one whose accreditation expired", () => {
    wayParts().then(({ methodId }) =>
      newParameter().then((parameter) => {
        const way = (subcontractor) => ({ parameter_id: parameter.id, method_id: methodId, subcontractor_id: subcontractor.id });
        cy.signInAs("administrator");
        refAs(ADMINISTRATOR, EXPIRED_SUBCONTRACTOR).then((expired) =>
          callRefused("medilab.parameter.method", "create", [way(expired)]).should(
            "match",
            /^The accreditation of Coastal .+ expired on .+\. Renew it before choosing this subcontractor\.$/,
          ),
        );
        archivedSubcontractor().then((archived) =>
          callRefused("medilab.parameter.method", "create", [way(archived)]).should("eq", "Mekong Food Testing is archived and cannot be chosen."),
        );
        call("medilab.parameter.method", "search_count", [[["parameter_id", "=", parameter.id]]]).should("eq", 0);
      }),
    );
  });

  it("TC-F37-01 lets a person with the subcontractor permission add its contact people", () => {
    const name = `Người liên hệ ${Date.now()}`;
    refAs(ADMINISTRATOR, "sol_demo.demo_subcontractor_southern_micro").then((subcontractor) => {
      step("The administrator adds a contact person to the subcontractor");
      cy.signInAs("administrator");
      cy.openRecord(subcontractor);
      cy.contains(".o_form_view .o_form_statusbar button:visible", "Add a Contact Person").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_field_widget[name=name] input").type(name);
        cy.get("button[name=action_add]").click();
      });
      cy.get(".modal").should("not.exist");
      cy.contains(".o_notebook .nav-link", "Contact People").click();
      cy.contains(".o_field_widget[name=contact_ids] .o_data_row", name).should("be.visible");
    });
  });

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
});

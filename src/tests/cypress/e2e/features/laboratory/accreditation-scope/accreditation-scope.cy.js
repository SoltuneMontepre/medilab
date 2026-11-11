import { callAs, callRefused, randomId, refAs } from "../../../../support/odoo";
import { pick } from "../../../../support/form";

const ADMINISTRATOR = "demo.administrator";
const CERTIFICATE = "sol_demo.demo_accreditation_certificate_valid";

function displayName(xmlId) {
  return refAs(ADMINISTRATOR, xmlId).then(({ model, id }) =>
    callAs(ADMINISTRATOR, model, "read", [[id], ["display_name"]]).then(([record]) => ({ id, name: record.display_name })),
  );
}

function accredited(model, domain) {
  return callAs(ADMINISTRATOR, model, "search_read", [domain], { fields: ["is_accredited"] }).then((records) =>
    records.map((record) => record.is_accredited),
  );
}

describe("Accreditation by method, parameter and sample type", () => {
  it("TC-F412-01: importing scope lines creates the method with its code as title and adds a line per row", () => {
    const code = `TCVN ${randomId().slice(0, 6)}:2026`;
    displayName("sol_demo.demo_testing_field_chemistry").as("field");
    displayName("sol_demo.demo_test_parameter_lead").as("lead");
    displayName("sol_demo.demo_sample_type_surface_water").as("water");

    cy.signInAs("administrator");
    cy.openRecord(CERTIFICATE);
    cy.get(".o_statusbar_buttons button[name=action_import_scope]").click();
    cy.get(".modal:visible").within(() => {
      cy.get("@field").then(({ name }) => pick("field_id", name));
      cy.get(".o_field_x2many_list_row_add button").click();
      cy.get(".o_field_widget[name=code] input").type(code);
      cy.get("@lead").then(({ name }) => pick("parameter_ids", name));
      cy.get("@water").then(({ name }) => pick("sample_type_ids", name));
      cy.get("button[name=action_import]").click();
    });
    cy.get(".modal").should("not.exist");
    cy.contains(".o_field_widget[name=scope_line_ids] .o_data_row", code).should("be.visible");

    callAs(ADMINISTRATOR, "medilab.testing.method", "search_read", [[["code", "=", code]]], { fields: ["name"] }).then(
      ([method]) => {
        expect(method.name, "title of a row left without one").to.equal(code);
        cy.get("@lead").then((lead) =>
          cy.get("@water").then((water) =>
            callAs(ADMINISTRATOR, "medilab.accreditation.scope.line", "search_read", [[["method_id", "=", method.id]]], {
              fields: ["parameter_ids", "sample_type_ids", "to_confirm"],
            }).then(([line]) => {
              expect(line).to.deep.include({ parameter_ids: [lead.id], sample_type_ids: [water.id], to_confirm: false });
            }),
          ),
        );
      },
    );

    // A row without a code refuses the whole import: the method of the other row is not created either.
    const other = `TCVN ${randomId().slice(0, 6)}:2026`;
    cy.get("@lead").then((lead) =>
      cy.get("@water").then((water) =>
        refAs(ADMINISTRATOR, CERTIFICATE).then(({ id }) => {
          const scope = { parameter_ids: [[6, 0, [lead.id]]], sample_type_ids: [[6, 0, [water.id]]] };
          cy.get("@field").then((field) =>
            callAs(ADMINISTRATOR, "medilab.accreditation.certificate.import", "create", [
              {
                certificate_id: id,
                field_id: field.id,
                lang: "en_US",
                line_ids: [
                  [0, 0, { code: other, ...scope }],
                  [0, 0, { code: "", ...scope }],
                ],
              },
            ]),
          ).then((wizardId) => {
            callRefused("medilab.accreditation.certificate.import", "action_import", [[wizardId]]).then((message) => {
              // The message is in the administrator's language and names the row without a code.
              expect(message).to.match(/^(Row|Dòng) 2 /);
            });
            callAs(ADMINISTRATOR, "medilab.testing.method", "search_count", [[["code", "=", other]]]).then((count) => {
              expect(count, "methods of the refused import").to.equal(0);
            });
          });
        }),
      ),
    );
  });

  it("TC-F412-02: a sample test is accredited only when one scope line covers its method, parameter and sample type", () => {
    // Lead by AAS on bottled water is on an exact line; Lead by ICP-MS on bottled water is covered through Food.
    refAs(ADMINISTRATOR, "sol_demo.demo_sample_test_lead_today").then(({ id }) =>
      accredited("medilab.sample.test", [["id", "=", id]]).then((marks) => expect(marks).to.deep.equal([true])),
    );
    refAs(ADMINISTRATOR, "sol_demo.demo_sample_test_lead_room_booked").then(({ id }) =>
      accredited("medilab.sample.test", [["id", "=", id]]).then((marks) => expect(marks).to.deep.equal([true])),
    );
    // The subcontracted way uses ICP-MS too, but a subcontracted test is outside the laboratory's scope.
    refAs(ADMINISTRATOR, "sol_demo.demo_parameter_method_lead_subcontracted").then(({ id }) =>
      accredited("medilab.sample.test", [["parameter_method_id", "=", id]]).then((marks) => {
        expect(marks, "subcontracted lead tests").not.to.be.empty;
        expect(marks).not.to.include(true);
      }),
    );
    // TCVN 7602 is on the certificate, but not for surface water: a method match alone is not enough.
    refAs(ADMINISTRATOR, "sol_demo.demo_parameter_method_sample_type_lead_aas_surface_water").then(({ id }) =>
      accredited("medilab.parameter.method.sample.type", [["id", "=", id]]).then((marks) =>
        expect(marks).to.deep.equal([false]),
      ),
    );

    cy.signInAs("administrator");
    cy.openRecord("sol_demo.demo_sample_test_lead_today");
    cy.get(".o_field_widget[name=is_accredited] input").should("be.checked");
  });
});

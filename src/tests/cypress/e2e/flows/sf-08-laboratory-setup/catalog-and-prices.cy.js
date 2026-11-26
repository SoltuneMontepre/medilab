import { newRecord, save } from "../../../support/form";
import { becomeVisitor, call, callRefused, refAs, resolveRecord } from "../../../support/odoo";
import { orderAt } from "../wf-01-order-to-test-request/setup";

describe("SF-08 catalog, prices and taxes (F-01, F-02)", () => {
  it("TC-F01-01 shows a parameter of a sub-group when the catalog is filtered by its parent group", () => {
    refAs("demo.administrator", "sol_demo.demo_parameter_group_pesticides").then((pesticides) => {
      becomeVisitor();
      cy.visit(`/catalog?group=${pesticides.id}`);
      cy.contains(".card h3", "Chlorpyrifos").should("be.visible");
      cy.contains(".card h3", "Lead (Pb)").should("not.exist");
    });
  });

  it("TC-F01-02 gives a record without a code one from its sequence and refuses a code already used", () => {
    const name = `Kim loại vết ${Date.now()}`;
    cy.signInAs("administrator");
    newRecord("/odoo/parameter-groups");
    cy.get(".o_field_widget[name=name] input").type(name);
    save();
    call("medilab.parameter.group", "search_read", [[["name", "=", name]]], { fields: ["code"] }).then(([group]) => {
      expect(group.code, "code from the sequence").not.to.be.oneOf([false, ""]);
      callRefused("medilab.parameter.group", "create", [{ name: `${name} 2`, code: group.code }]).should(
        "contain",
        "The code of a parameter group must be unique.",
      );
    });
  });

  it("TC-F02-02 refuses overlapping VAT rate periods", () => {
    cy.signInAs("administrator");
    resolveRecord("sol_demo.demo_tax_vat10").then((tax) => {
      callRefused("medilab.tax.rate", "create", [{ tax_id: tax.id, rate: 9, valid_from: "2025-06-01" }]).should(
        "match",
        /^The rate periods of .* overlap: /,
      );
    });
  });

  it("TC-F02-03 does not offer a parameter without a price and tax", () => {
    cy.visit("/catalog");
    cy.contains(".card h3", "Lead (Pb)").should("be.visible");
    cy.contains(".card h3", "Chromium (VI)").should("not.exist");
    orderAt("claimed").then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.intercept("POST", "/web/dataset/call_kw/product.*/*search*").as("productSearch");
      cy.get(".o_field_widget[name=product_line_ids] .o_field_x2many_list_row_add button").first().click();
      cy.get(".o_selected_row .o_field_widget[name=product_template_id] input").type("Cadmi");
      cy.wait("@productSearch")
        .its("response.body")
        .should((body) => {
          expect(body.error).to.be.undefined;
          expect(JSON.stringify(body.result)).not.to.contain("Cadmium");
        });
    });
  });
});

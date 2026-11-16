import { becomeVisitor, call, callAs, callRefused, refAs } from "../../../support/odoo";
import { CUSTOMERS, clearCarts, orderAt } from "./setup";

describe("WF-01 portal cart and order claiming (F-04, F-05)", () => {
  it("TC-F04-02 orders a package whole with its parameters", () => {
    clearCarts(CUSTOMERS.nuocSach);
    cy.signInAs("customer");
    cy.visit("/catalog");
    cy.contains("tr", "Bottled water basic").find("button[type=submit]").click();
    cy.location("pathname").should("eq", "/cart");
    cy.get("form[action='/cart/line']").should("have.length", 1);
    cy.contains("tr", "Bottled water basic").find("form[action='/cart/line']").should("exist");
    refAs("demo.head_of_sales", CUSTOMERS.nuocSach.company)
      .then(({ id }) =>
        callAs(
          "demo.head_of_sales",
          "sale.order.line",
          "search_read",
          [
            [
              ["order_id.customer_id", "=", id],
              ["order_id.order_status", "=", "draft"],
            ],
          ],
          {
            fields: ["product_id", "price_unit", "linked_line_id"],
          },
        ),
      )
      .should((lines) => {
        const parts = lines.filter((line) => line.linked_line_id);
        expect(parts, "parameters of the package").not.to.be.empty;
        expect(
          parts.every((part) => part.price_unit === 0),
          "parameters priced in the package",
        ).to.be.true;
      });
    clearCarts(CUSTOMERS.nuocSach);
  });

  it("TC-F04-03 refuses a cart submitted without an e-mail address", () => {
    becomeVisitor();
    cy.contains("tr", "Lead (Pb)").find("button[type=submit]").click();
    cy.get("form[action='/cart/submit'] input[name=email]").should("have.attr", "required");
    // The browser asks for the address first; the server refuses a form sent without it all the same.
    cy.get("form[action='/cart/submit'] input[name=email]").invoke("removeAttr", "required");
    cy.get("form[action='/cart/submit'] input[name=name]").type("Lê Văn Khách");
    cy.get("form[action='/cart/submit'] button[type=submit]").first().click();
    cy.location("pathname").should("eq", "/cart");
    cy.contains("p.text-danger", "Enter an e-mail address.");
    cy.get("form[action='/cart/submit']").should("exist");
  });

  it("TC-F05-02 lets a salesperson who reads every order read another salesperson's order without changing it", () => {
    refAs("demo.administrator", "sol_demo.demo_sale_order_history_sales_2_1").then((other) => {
      cy.signInAs("sales");
      call("sale.order", "read", [[other.id], ["name", "order_can_edit"]]).then(([read]) => {
        expect(read.name).to.match(/^S\d+/);
        expect(read.order_can_edit).to.be.false;
      });
      callRefused("sale.order", "write", [[other.id], { note: "Changed by another salesperson" }]).should("match", /S\d+/);
      cy.visit("/odoo/unclaimed-orders");
      cy.get(".o_data_row").should("have.length.greaterThan", 0);
      cy.signInAs("head_of_sales");
      cy.readRecord(other, ["name"]).its("name").should("match", /^S\d+/);
    });
  });

  it("TC-F05-03 refuses to claim an order another salesperson already claimed", () => {
    orderAt("claimed").then((order) => {
      cy.signInAs("head_of_sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_claim]").should("not.exist");
      callRefused("sale.order", "action_claim", [[order.id]]).should("eq", "This order is already claimed.");
      cy.readRecord(order, ["user_id"]).its("user_id.1").should("eq", "Nguyen Thi Thu");
    });
  });
});

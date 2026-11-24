import { becomeVisitor, callAs, refAs } from "../../../support/odoo";
import { orderAt } from "../wf-01-order-to-test-request/setup";

describe("SF-09 customer accounts and profiles (F-03)", () => {
  it("TC-F03-01 lets a newly registered customer sign in and see only their own documents", () => {
    const login = `khach.moi.${Date.now()}@example.com`;
    orderAt("sent").then((order) => {
      becomeVisitor();
      cy.visit("/web/signup");
      cy.get("input[name=name]").type("Đỗ Văn Mới");
      cy.get("input[name=login]").type(login);
      cy.get("input[name=password]").type("signup-pass-12", { log: false });
      cy.get("input[name=confirm_password]").type("signup-pass-12", { log: false });
      cy.get("select[name=customer_type]").select("business");
      cy.get("input[name=company_name]").type(`Công ty Mới ${Date.now()}`);
      cy.get("input[name=vat]").type(`03${String(Date.now()).slice(-8)}`);
      cy.get("input[name=phone]").type("028 3999 1234");
      cy.get("input[name=street]").type("1 Lê Lợi");
      cy.get("input[name=city]").type("Hồ Chí Minh");
      cy.get("form").filter(":has(input[name=confirm_password])").find("button[type=submit]").click();
      cy.location("pathname").should("not.eq", "/web/signup");
      cy.visit("/orders");
      cy.get("body").should("not.contain", order.name || `S${order.id}`);
      cy.request({ url: `/orders/${order.id}`, failOnStatusCode: false })
        .its("status")
        .should("eq", 404);
    });
  });

  it("TC-F03-03 denies another customer the quotation, invoice and result", () => {
    orderAt("paid").then((order) => {
      refAs("demo.administrator", "sol_demo.demo_test_report_by_email").then((report) => {
        callAs("demo.sales", "sale.order", "read", [[order.id], ["invoice_ids"]]).then(([read]) => {
          const invoiceIds = read.invoice_ids;
          expect(invoiceIds, "invoices of the paid order").not.to.be.empty;
          callAs("demo.accountant", "account.move", "read", [invoiceIds, ["name"]]).then((invoices) => {
            cy.signInAs("individual");
            cy.request({ url: `/orders/${order.id}/quotation`, failOnStatusCode: false }).its("status").should("eq", 404);
            invoices.forEach((invoice) => {
              cy.request({ url: `/my/invoices/${invoice.id}`, failOnStatusCode: false }).should((response) => {
                expect(response.redirects, "sent back to the portal home").not.to.be.empty;
                expect(response.body).not.to.contain(invoice.name);
              });
            });
          });
        });
        cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false }).its("status").should("eq", 404);
      });
    });
  });
});

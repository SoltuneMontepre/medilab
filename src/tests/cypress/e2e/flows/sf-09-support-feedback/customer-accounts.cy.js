import { becomeVisitor, refAs } from "../../../support/odoo";
import { latestQuotation, orderAt } from "../wf-01-order-to-test-request/setup";

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
    orderAt("sent").then((order) => {
      cy.signInAs("sales");
      latestQuotation(order.id).then((quotation) => {
        refAs("demo.administrator", "sol_demo.demo_test_report_by_email").then((report) => {
          cy.signInAs("individual");
          cy.request({ url: `/orders/${order.id}/quotation`, failOnStatusCode: false })
            .its("status")
            .should("eq", 404);
          const [invoiceId, invoiceName] = quotation.advance_invoice_id;
          cy.request(`/my/invoices/${invoiceId}`).should((response) => {
            expect(response.redirects, "sent back to the portal home").not.to.be.empty;
            expect(response.body).not.to.contain(invoiceName);
          });
          cy.request({ url: `/my/test-reports/${report.id}/download`, failOnStatusCode: false })
            .its("status")
            .should("eq", 404);
        });
      });
    });
  });
});

import { openTab } from "../../../support/form";
import { callAs, callRefused } from "../../../support/odoo";
import { SAMPLING_LINES, latestQuotation, orderAt } from "./setup";

describe("WF-01 advance payment and order confirmation (F-09, F-10)", () => {
  it("TC-F09-02 accepts a payment up to the amount still owed and refuses more", () => {
    orderAt("sent").then((order) => {
      cy.signInAs("sales");
      latestQuotation(order.id).then(({ advance_invoice_id: [invoice] }) => {
        cy.signInAs("customer");
        cy.visit(`/my/invoices/${invoice}`);
        cy.get("#medilab_payment_amount").invoke("attr", "max").then(Number).as("owed");
        cy.get("#medilab_payment_amount").invoke("removeAttr", "max");
        cy.get("@owed").then((owed) =>
          cy
            .get("#medilab_payment_amount")
            .clear()
            .type(String(owed + 1000)),
        );
        cy.intercept("POST", `/my/invoices/${invoice}/pay`).as("pay");
        cy.get("button[name=method][value=bank_transfer]").click();
        cy.wait("@pay");
        cy.visit(`/my/invoices/${invoice}`);
        cy.get("#medilab_payment_amount").clear().type("10000");
        cy.get("button[name=method][value=bank_transfer]").click();
        cy.wait("@pay");
        callAs("demo.accountant", "account.payment", "search_read", [[["invoice_ids", "in", [invoice]]]], { fields: ["amount", "state"] }).should(
          (payments) => expect(payments.map((payment) => payment.amount)).to.deep.equal([10000]),
        );
      });
    });
  });

  it("TC-F10-01 carries the accepted quotation's expected samples to the test request", () => {
    orderAt("confirmed", { lines: SAMPLING_LINES }).then((order) => {
      callAs("demo.sales", "sale.order", "read", [[order.id], ["test_request_id"]]).then(([read]) => {
        cy.signInAs("sample_delivery_staff");
        cy.readRecord({ model: "medilab.test.request", id: read.test_request_id[0] }, ["sample_ids"]).then(({ sample_ids }) => {
          expect(sample_ids, "samples of the request").to.have.length(1);
          const sample = { model: "medilab.sample", id: sample_ids[0] };
          cy.readRecord(sample, ["expected_sample_count"]).its("expected_sample_count").should("eq", 6);
          cy.openRecord(sample);
          openTab("expected_sampling");
          cy.get(".o_field_widget[name=expected_sample_count]").should("contain", "6");
          cy.get(".o_field_widget[name=expected_sampling_ids] .o_data_row").should("have.length", 2);
        });
      });
    });
  });

  it("TC-F10-02 starts collecting samples as soon as the order is confirmed", () => {
    orderAt("accepted", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]").should("not.exist");
      callRefused("sale.order", "action_start_sample_collection", [[order.id]]).should("eq", "Đơn hàng phải được xác nhận trước khi thu mẫu.");
      cy.get(".o_statusbar_buttons button[name=action_confirm_order]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").click();
      cy.readRecord(order, ["order_status"]).its("order_status").should("eq", "confirmed");
    });
  });

  it("TC-F10-02 refuses to confirm the test request of an unpaid order without credit", () => {
    orderAt("confirmed", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.readRecord(order, ["test_request_id"]).then(({ test_request_id: [id, code] }) => {
        const request = { model: "medilab.test.request", id };
        cy.signInAs("sample_delivery_staff");
        cy.openRecord(request);
        cy.expectRefusal({
          read: () => cy.readRecord(request, ["status", "write_date"]),
          action: () => cy.get(".o_statusbar_buttons button[name=action_confirm]:visible").click(),
          message: `Test request ${code} cannot be confirmed until its order is paid or the customer is allowed credit.`,
        });
      });
    });
  });
});

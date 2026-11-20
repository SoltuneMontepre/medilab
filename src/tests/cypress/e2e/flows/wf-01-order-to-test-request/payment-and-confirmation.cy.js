import { openTab } from "../../../support/form";
import { callAs, callRefused } from "../../../support/odoo";
import { CUSTOMERS, SAMPLING_LINES, orderAt, payAdvance } from "./setup";

describe("WF-01 order confirmation and test request (F-10)", () => {
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
    orderAt("accepted", { advance: false, customer: CUSTOMERS.anPhu }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]").should("not.exist");
      callRefused("sale.order", "action_start_sample_collection", [[order.id]]).should("eq", "Đơn hàng phải được xác nhận trước khi thu mẫu.");
      cy.get(".o_statusbar_buttons button[name=action_confirm_order]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").click();
      // Sales enters when and where the samples are collected; the address starts as the customer's.
      cy.get(".modal .o_field_widget[name=address] textarea").invoke("val").should("not.be.empty");
      cy.get(".modal .o_field_widget[name=appointment] input").type("31/12/2099 09:00").type("{enter}");
      cy.get(".modal button[name=action_start]").click();
      cy.get(".modal").should("not.exist");
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]").should("not.exist");
      cy.readRecord(order, ["order_status"]).its("order_status").should("eq", "confirmed");
    });
  });

  it("TC-F10-02 holds the sample collection of a portal order until its balance is paid", () => {
    orderAt("confirmed", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.readRecord(order, ["payment_status", "balance_due"]).should((read) => {
        expect(read.payment_status).not.to.equal("paid");
        expect(read.balance_due).to.equal("before_collection");
      });
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]").should("not.exist");
      payAdvance(order);
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").should("exist");
    });
  });
});

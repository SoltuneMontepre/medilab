import { openTab } from "../../../support/form";
import { callAs, callRefused } from "../../../support/odoo";
import { CUSTOMERS, SAMPLING_LINES, orderAt } from "./setup";

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
      cy.readRecord(order, ["order_status"]).its("order_status").should("eq", "confirmed");
    });
  });

  it("TC-F10-02 keeps an unpaid test request unconfirmable for a customer without credit", () => {
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

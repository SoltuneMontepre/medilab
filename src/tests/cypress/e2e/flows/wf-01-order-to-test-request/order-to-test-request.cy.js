import { choose, newRecord, openMenu, openRow, openTab, pick, save, search } from "../../../support/form";
import { MENU, PORTAL_MENU } from "../../../support/menus";
import { becomeVisitor, call, callAs, callRefused, refAs, resolveRecord, signIn } from "../../../support/odoo";
import { step } from "../../../support/steps";
import {
  CUSTOMERS,
  SAMPLING_LINES,
  clearCarts,
  currentRequest,
  declineQuotation,
  latestQuotation,
  orderAt,
  payAdvance,
  requestPaymentPath,
  reviseQuotation,
} from "./setup";

const REASON = "Giá xét nghiệm chì cao hơn báo giá năm trước.";

const ORDER_FIELDS = ["order_status", "quotation_follow_up", "write_date"];

const readOrder =
  (order, fields = ORDER_FIELDS) =>
  () =>
    cy.readRecord(order, fields);

// The expected samples a page shows inside `container`: one sample with its objects, expected samples and groups.
function expectSampling(container, { objects, expected, groups }) {
  cy.get(container)
    .find(".o_medilab_expected_sampling")
    .within(() => {
      cy.get(".o_medilab_objects").should("have.text", String(objects));
      cy.get(".o_medilab_expected").should("have.text", String(expected));
      cy.get("tbody tr").should("have.length", groups);
    });
}
// The advance request keeps the exact quotation deadline.
function expectAdvanceDueOnDeadline(order) {
  cy.readRecord(order, ["payment_deadline"]).then(({ payment_deadline }) => currentRequest(order).its("deadline").should("eq", payment_deadline));
}

describe("WF-01 Order to confirmed test request", () => {
  it("TC-WF01-M takes a portal order through the quotation, payment and confirmation", () => {
    const sampleName = `Mẫu nước ${Date.now()}`;
    clearCarts(CUSTOMERS.nuocSach);
    step("Customer fills a cart from the catalog");
    cy.signInAs("customer");
    cy.get(`${PORTAL_MENU} a[href='/catalog']`).click();
    cy.contains("tr", "Lead (Pb)").find("button[type=submit]").click();
    cy.location("pathname").should("eq", "/cart");
    step("Customer chooses the sample type and submits the order");
    // The customer chooses the sample type, and the parameter's default way of testing on it is filled in.
    cy.get("select[name=sample_type_id]")
      .first()
      .find("option")
      .contains(/Nước đóng chai|Bottled water/)
      .invoke("val")
      .then((value) => cy.get("select[name=sample_type_id]").first().select(String(value)));
    cy.get("select[name=parameter_method_id]").first().invoke("val").should("not.be.empty");
    cy.get("form[action='/cart/submit'] button[type=submit]").first().click();
    cy.contains("h1", "Order submitted");
    cy.contains("p", "is in the sales queue.")
      .invoke("text")
      .then((text) => {
        const name = text.match(/S\d+/)[0];
        step("Sales claims the order from the unclaimed queue");
        cy.signInAs("sales");
        return call("sale.order", "search_read", [[["name", "=", name]]], { fields: ["name", "order_status"] });
      })
      .then(([submitted]) => {
        expect(submitted.order_status).to.equal("submitted");
        const order = { model: "sale.order", id: submitted.id };
        openMenu(MENU.sales, MENU.unclaimedOrders);
        // The queue lists the oldest orders first, so earlier runs can push this one to a later page.
        search(submitted.name);
        cy.contains(".o_data_row", submitted.name).find("button[name=action_claim]").click();
        cy.contains(".o_data_row", submitted.name).should("not.exist");

        step("Sales opens the order and puts its parameter on a sample");
        openMenu(MENU.sales, MENU.orders);
        openRow(submitted.name);
        openTab("samples");
        cy.get(".o_field_widget[name=sample_ids] .o_field_x2many_list_row_add button").click();
        cy.get(".o_selected_row .o_field_widget[name=customer_sample_name] input").type(sampleName);
        pick("sample_type_id", "Nước đóng chai");
        choose("physical_state", "Lỏng");
        save();
        openTab("order_lines");
        cy.get(".o_field_widget[name=product_line_ids] .o_data_row td[name=sample_id]").first().click();
        pick("sample_id", sampleName);
        step("Sales asks for an online advance and sends the quotation");
        openTab("payment");
        choose("advance_method", "Trực tuyến");
        choose("advance_mode", "Phần trăm");
        cy.get(".o_field_widget[name=advance_value] input").clear().type("30");
        cy.sendRecord("action_send_quotation");
        cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");
        cy.readRecord(order, ["invoice_ids"]).its("invoice_ids").should("be.empty");
        call(
          "sale.order.line",
          "search_read",
          [
            [
              ["order_id", "=", order.id],
              ["linked_line_id", "=", false],
            ],
          ],
          {
            fields: ["parameter_method_id", "is_downpayment"],
          },
        ).then((lines) => lines.filter((line) => !line.is_downpayment).forEach((line) => expect(line.parameter_method_id).to.be.ok));
        expectAdvanceDueOnDeadline(order);
        latestQuotation(order.id).then((quotation) => {
          expect(quotation.status).to.equal("sent");
          expect(quotation.payment_request_ids).to.have.length(1);
          cy.signInAs("customer");
          cy.visit(`/orders/${order.id}/quotation`);
          cy.contains("h2", "Advance payment request");
          cy.get("button[name=method][value=payos]").click();
          cy.get("#payos-pending").should("be.visible");
        });
      });

    // PayOS never answers a local demo, so the order confirmed below is one whose advance is already paid.
    step("Sales confirms a paid order, which creates its test request");
    orderAt("accepted").then((paid) => {
      cy.signInAs("sales");
      cy.openRecord(paid);
      cy.intercept("POST", "**/web/dataset/call_button/sale.order/action_confirm_order*").as("confirmOrder");
      cy.get(".o_statusbar_buttons button[name=action_confirm_order]:visible").click();
      cy.wait("@confirmOrder").its("response.body").should("not.have.property", "error");
      // Its advance is verified, so its samples can be collected; the balance request waits for the report.
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").should("exist");
      currentRequest(paid).its("kind").should("eq", "balance");
      payAdvance(paid);
      cy.openRecord(paid);
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").should("exist");
      cy.readRecord(paid, ["order_status", "test_request_id", "sample_ids"]).then((read) => {
        expect(read.order_status).to.equal("confirmed");
        call("medilab.test.request", "read", [[read.test_request_id[0]], ["status", "sample_ids"]]).then(([request]) =>
          expect(request.sample_ids).to.have.length(read.sample_ids.length),
        );
      });
      callRefused("sale.order", "write", [[paid.id], { validity_date: "2099-12-31" }]).should("eq", "Không thể thay đổi đơn hàng đã xác nhận.");
    });
  });

  it("TC-WF01-A1 lets sales create the order for a customer who called", () => {
    step("Sales creates an order for the customer who called");
    cy.signInAs("sales");
    newRecord("/odoo/lab-orders");
    pick("customer_id", "Công ty TNHH Nước Uống Sạch");
    pick("partner_id", "Phạm Thị Hoa");
    step("Sales adds Lead (Pb), whose price fills in, and saves the order");
    cy.get(".o_field_widget[name=product_line_ids] .o_field_x2many_list_row_add button").first().click();
    pick("product_template_id", "Lead (Pb)");
    cy.get(".o_field_widget[name=product_line_ids] .o_data_row").should("contain", "280.000");
    save();
    step("The order comes from sales and is already claimed by its salesperson");
    cy.location("pathname")
      .then((path) => cy.readRecord({ model: "sale.order", id: Number(path.split("/").pop()) }, ["source", "order_status", "user_id"]))
      .should((read) => {
        expect(read.source).to.equal("sales");
        expect(read.order_status).to.equal("claimed");
        expect(read.user_id[1]).to.equal("Nguyen Thi Thu");
      });
  });

  it("TC-WF01-A2 lets a visitor who is not signed in submit a cart with their details", () => {
    const email = `visitor.${Date.now()}@example.com`;
    step("A visitor who is not signed in adds Lead (Pb) to a cart");
    becomeVisitor();
    cy.contains("tr", "Lead (Pb)").find("button[type=submit]").click();
    step("The visitor gives a name and an e-mail address and submits the cart");
    cy.get("form[action='/cart/submit'] input[name=name]").type("Lê Văn Khách");
    cy.get("form[action='/cart/submit'] input[name=email]").type(email);
    cy.get("form[action='/cart/submit'] button[type=submit]").first().click();
    cy.contains("h1", "Order submitted");
    step("The order waits unclaimed in the sales queue");
    callAs("demo.head_of_sales", "sale.order", "search_read", [[["partner_id.email", "=", email]]], {
      fields: ["order_status", "source", "user_id"],
    }).should(([order]) => {
      expect(order.order_status).to.equal("submitted");
      expect(order.source).to.equal("portal");
      expect(order.user_id).to.equal(false);
    });
  });

  it("TC-WF01-A3 lets a returning customer reorder, and sales create the order from a template", () => {
    clearCarts(CUSTOMERS.nuocSach);
    step("A returning customer reorders a completed order");
    cy.signInAs("customer");
    resolveRecord("sol_demo.demo_sale_order_completed").then((completed) => {
      cy.visit(`/orders/${completed.id}`);
      cy.get("form[action$='/reorder'] button").click();
      cy.location("pathname")
        .should("match", /^\/orders\/\d+$/)
        .and("not.eq", `/orders/${completed.id}`);
      step("The reorder is a new draft, and the completed order stays as it was");
      cy.signInAs("head_of_sales");
      call("sale.order", "search_read", [[["reordered_from_id", "=", completed.id]]], {
        fields: ["order_status", "order_line"],
        order: "id desc",
        limit: 1,
      }).should(([reorder]) => {
        expect(reorder.order_status).to.equal("draft");
        expect(reorder.order_line).not.to.be.empty;
      });
      cy.readRecord(completed, ["order_status"]).its("order_status").should("eq", "completed");
    });
    clearCarts(CUSTOMERS.nuocSach);

    step("Sales creates an order from the customer's template");
    cy.signInAs("sales");
    cy.openRecord("sol_demo.demo_order_template_monthly_water");
    cy.get(".o_statusbar_buttons button[name=action_create_order]:visible").click();
    step("The new order is an unsent draft");
    cy.location("pathname")
      .should("match", /sale\.order\/\d+$/)
      .then((path) => cy.readRecord({ model: "sale.order", id: Number(path.split("/").pop()) }, ["order_status", "state", "quotation_ids"]))
      .should((read) => {
        expect(read.state).to.equal("draft");
        expect(read.quotation_ids).to.be.empty;
      });
  });

  it("TC-WF01-A4 lets sales revise a declined quotation and send the version the customer accepts", () => {
    orderAt("sent").then((order) => {
      step("The customer declines the quotation with a reason");
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}/quotation`);
      cy.get("form[action$='/quotation/decline'] textarea[name=reason]").type(REASON);
      cy.get("form[action$='/quotation/decline'] button").click();
      cy.contains("p", `Reason for declining: ${REASON}`);

      step("Sales revises the quotation and sends the new version");
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.intercept("POST", "**/web/dataset/call_button/sale.order/action_send_quotation*").as("sendRevision");
      cy.sendRecord("action_send_quotation");
      cy.wait("@sendRevision").its("response.body").should("not.have.property", "error");
      latestQuotation(order.id).its("revision").should("eq", 2);
      step("The customer accepts the new version by paying its advance");
      payAdvance(order);
      step("The first version is replaced, and the new one is accepted");
      cy.signInAs("sales");
      call("medilab.quotation", "search_read", [[["order_id", "=", order.id]]], { fields: ["revision", "status"], order: "revision" }).should(
        (quotations) => expect(quotations.map((quotation) => quotation.status)).to.deep.equal(["replaced", "accepted"]),
      );
    });
  });

  it("TC-WF01-A6 flags an expired quotation, which sales extends", () => {
    orderAt("sent").then((order) => {
      const yesterday = new Date(Date.now() - 86400000).toISOString().replace("T", " ").slice(0, 19);
      step("The quotation passes its payment deadline and is flagged expired");
      callAs("demo.sales", "sale.order", "write", [[order.id], { payment_deadline: yesterday }]);
      refAs("demo.administrator", "sol_commerce.cron_flag_expired_quotations").then(({ id }) =>
        callAs("demo.administrator", "ir.cron", "method_direct_trigger", [[id]]),
      );
      step("Sales extends the deadline of the expired quotation");
      cy.signInAs("sales");
      cy.readRecord(order, ["quotation_follow_up"]).its("quotation_follow_up").should("eq", "expired");
      cy.openRecord(order);
      // The 15th of the month after the expired deadline is always after today.
      cy.get(".o_field_widget[name=payment_deadline] button").click();
      cy.get(".o_datetime_picker .o_header_part")
        .invoke("text")
        .then((month) => {
          cy.get(".o_datetime_picker .o_next").click();
          cy.get(".o_datetime_picker .o_header_part").should("not.have.text", month);
        });
      cy.contains(".o_datetime_picker .o_date_item_cell:not(.o_out_of_range)", /^15$/).click();
      cy.contains(".o_datetime_picker button", "Áp dụng").click();
      save();
      step("The quotation waits for payment again, its advance due on the new deadline");
      cy.readRecord(order, ["quotation_follow_up"]).its("quotation_follow_up").should("eq", "unpaid");
      expectAdvanceDueOnDeadline(order);
    });
  });

  it("TC-WF01-A5 lets the Head of Sales send without an advance to a credit customer, whose order goes ahead unpaid", () => {
    orderAt("claimed", { customer: CUSTOMERS.anPhu }).then((order) => {
      step("The Head of Sales sends the quotation without an advance");
      cy.signInAs("head_of_sales");
      cy.openRecord(order);
      openTab("payment");
      choose("advance_method", "No advance");
      cy.sendRecord("action_send_quotation");
      cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");

      step("The customer allowed to order on credit accepts the quotation on the portal");
      signIn("portal.anphu");
      cy.visit(`/orders/${order.id}/quotation`);
      cy.get("form[action$='/quotation/accept'] button").click();
      cy.contains("Status: Accepted");
      cy.readRecord(order, ["quotation_follow_up"]).its("quotation_follow_up").should("eq", "accepted");

      step("Sales confirms the unpaid order");
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_confirm_order]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").should("exist");
      cy.readRecord(order, ["payment_status", "test_request_id"]).then(({ payment_status, test_request_id: [id] }) => {
        expect(payment_status).to.equal("not_paid");
        step("Sample delivery staff confirm its test request without payment");
        cy.signInAs("sample_delivery_staff");
        cy.openRecord({ model: "medilab.test.request", id });
        cy.readRecord({ model: "medilab.test.request", id }, ["status"]).its("status").should("eq", "on_credit");
      });
    });
  });
});

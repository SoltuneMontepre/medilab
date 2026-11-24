import { openTab, save } from "../../../support/form";
import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { CUSTOMERS, REASON, SAMPLING_LINES, declineQuotation, orderAt, reviseQuotation } from "./setup";

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

describe("WF-01 quotation, revisions and templates (F-06, F-07)", () => {
  it("TC-F06-01 lets sales give a line and the whole quotation a discount before sending it", () => {
    orderAt("claimed").then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      openTab("order_lines");
      cy.get(".o_field_widget[name=product_line_ids] .o_data_row td[name=discount]").first().click();
      cy.get(".o_selected_row .o_field_widget[name=discount] input").clear().type("10");
      save();
      cy.get("button[name=action_open_discount_wizard]:visible").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_field_widget[name=discount_type] input[data-value=so_discount]").check();
        cy.get(".o_field_widget[name=discount_percentage] input").clear().type("5");
        cy.get("button[name=action_apply_discount]").click();
      });
      cy.get(".modal").should("not.exist");
      cy.get(".o_field_widget[name=product_line_ids] .o_data_row").should("have.length", 2);
      call("sale.order", "write", [[order.id], { advance_method: "bank_transfer", advance_mode: "percentage", advance_value: 30 }]);
      cy.reload();
      cy.sendRecord("action_send_quotation");
      cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");
      cy.get("button[name=action_open_discount_wizard]:visible").should("not.exist");
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}/quotation`);
      cy.contains("td", /^10(\.0+)?%$/).should("be.visible");
      cy.contains("td", /(Discount|Chiết khấu) 5(\.0+)?%/).should("be.visible");
    });
  });

  it("TC-F06-01 shows sales and the customer the expected samples: 3 objects in two groups make 6", () => {
    orderAt("claimed", { lines: SAMPLING_LINES }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      openTab("samples");
      expectSampling(".o_field_widget[name=expected_sampling_html]", { objects: 3, expected: 6, groups: 2 });
      callAs("demo.sales", "sale.order", "write", [[order.id], { advance_method: "bank_transfer", advance_mode: "percentage", advance_value: 30 }]);
      cy.reload();
      cy.sendRecord("action_send_quotation");
      cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");

      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}/quotation`);
      expectSampling("main", { objects: 3, expected: 6, groups: 2 });
    });
  });

  it("TC-F06-02 keeps a sent quotation's lines unchanged until it is revised", () => {
    orderAt("sent").then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.expectRefusal({
        read: () => call("sale.order.line", "search_read", [[["order_id", "=", order.id]]], { fields: ["price_unit", "discount", "tax_ids"] }),
        action: () => {
          cy.get(".o_field_widget[name=product_line_ids] .o_data_row td[name=price_unit]").first().click();
          cy.get(".o_selected_row .o_field_widget[name=price_unit] input").clear().type("100000");
          cy.get(".o_form_button_save").click();
        },
        message: "Báo giá đã được gửi; hãy sửa đổi báo giá trước khi sửa các dòng hoặc mẫu của đơn hàng.",
      });
    });
  });

  it("TC-F06-02 refuses to send or change the old version of a revised quotation", () => {
    orderAt("sent").then((order) => {
      declineQuotation(order, REASON);
      reviseQuotation(order);
      cy.signInAs("sales");
      cy.openRecord(order);
      openTab("revisions");
      cy.contains(".o_field_widget[name=quotation_ids] .o_data_row", "Đã thay thế").should("be.visible");
      call("medilab.quotation", "search", [
        [
          ["order_id", "=", order.id],
          ["revision", "=", 1],
        ],
      ]).then(([replaced]) => {
        callRefused("medilab.quotation", "action_send", [[replaced]]).should(
          "eq",
          "Báo giá đã được thay thế không thể gửi. Hãy gửi bản sửa đổi hiện tại.",
        );
        callRefused("medilab.quotation", "write", [[replaced], { decline_reason: REASON }]).should(
          "eq",
          "Báo giá đã được thay thế không thể thay đổi.",
        );
      });
    });
  });

  it("TC-F06-03 refuses to send a quotation without lines", () => {
    cy.signInAs("sales");
    refAs("demo.sales", CUSTOMERS.nuocSach.company)
      .then(({ id }) =>
        callAs(
          "demo.sales",
          "sale.order",
          "create",
          [{ customer_id: id, partner_id: id, advance_method: "bank_transfer" }],
          { context: { medilab_sales_order: true } },
        ),
      )
      .then((id) => {
        const order = { model: "sale.order", id };
        cy.openRecord(order);
        cy.expectRefusal({
          read: readOrder(order),
          action: () => cy.sendRecord("action_send_quotation"),
          message: "Thêm ít nhất một chỉ tiêu hoặc nhóm dịch vụ trước khi gửi báo giá.",
        });
      });
  });

  it("TC-F06-03 refuses to send a quotation with a line of no sample type", () => {
    orderAt("claimed", { sample: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.expectRefusal({
        read: readOrder(order),
        action: () => cy.sendRecord("action_send_quotation"),
        message: "Chọn loại mẫu cho các mục sau trước khi gửi báo giá:",
      });
    });
  });

  it("TC-F07-01 saves an order as a template", () => {
    const name = `Kiểm tra nước định kỳ ${Date.now()}`;
    orderAt("claimed").then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_save_as_template]:visible").click();
      cy.get(".modal .o_field_widget[name=name] input").clear().type(name);
      cy.get(".modal button[name=action_save]").click();
      cy.get(".modal").should("not.exist");
      call("medilab.order.template", "search_read", [[["name", "=", name]]], { fields: ["source_order_id"] }).should(([template]) =>
        expect(template.source_order_id[0]).to.equal(order.id),
      );
    });
  });

  it("TC-F07-03 does not let a salesperson open another salesperson's templates", () => {
    refAs("demo.administrator", "sol_demo.demo_order_template_monthly_water").then((template) => {
      cy.signInAs("sales_2");
      callRefused("medilab.order.template", "read", [[template.id], ["name"]]).should("contain", "medilab.order.template");
      cy.visit("/odoo/order-templates");
      cy.get(".o_list_renderer").should("not.contain", "Monthly water check");
    });
  });
});

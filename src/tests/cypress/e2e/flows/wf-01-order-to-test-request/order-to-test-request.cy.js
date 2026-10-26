import { call, callAs, callRefused, refAs, resolveRecord, signIn } from "../../../support/odoo";
import { CUSTOMERS, clearCarts, declineQuotation, latestQuotation, orderAt, payAdvance, reviseQuotation } from "./setup";

const REASON = "Giá xét nghiệm chì cao hơn báo giá năm trước.";

const ORDER_FIELDS = ["order_status", "approval_status", "quotation_follow_up", "write_date"];

const readOrder =
  (order, fields = ORDER_FIELDS) =>
  () =>
    cy.readRecord(order, fields);

// Picks a many2one value in the edited form or list row.
function pick(field, text) {
  cy.get(`.o_field_widget[name=${field}] input`).clear().type(text);
  cy.contains(".o-autocomplete--dropdown-item a", text).click();
}

// Picks a selection value in the edited form or list row by its label.
function choose(field, label) {
  cy.get(`.o_field_widget[name=${field}] .o_select_menu_toggler`).click();
  cy.contains(".o_select_menu_item", label).click();
  cy.get(`.o_field_widget[name=${field}] .o_select_menu_toggler`).should("have.value", label);
}

function save() {
  cy.get(".o_form_button_save").click();
  cy.get(".o_form_button_save").should("not.be.visible");
}

// Leaves the back office for a portal page, which sends no requests of its own, then signs out.
function becomeVisitor() {
  cy.visit("/catalog");
  cy.clearCookies();
}

// A visitor's first page and the requests it starts can each open a session; the forms need the one that stays.
function visitCatalogAsVisitor() {
  cy.visit("/catalog");
  cy.getCookie("session_id").should("exist");
  cy.visit("/catalog");
}

function openTab(name) {
  cy.get(`.o_notebook .nav-link[name=${name}]`).click();
}

describe("WF-01 Order to approved test request", () => {
  it("TC-WF01-M takes a portal order through the quotation, payment and approval", () => {
    const sampleName = `Mẫu nước ${Date.now()}`;
    clearCarts(CUSTOMERS.nuocSach);
    cy.signInAs("customer");
    cy.visit("/catalog");
    cy.contains("tr", "Lead (Pb)").find("button[type=submit]").click();
    cy.location("pathname").should("eq", "/cart");
    cy.get("form[action='/cart/submit'] button[type=submit]").first().click();
    cy.contains("h1", "Order submitted");
    cy.contains("p", "is in the sales queue.")
      .invoke("text")
      .then((text) => {
        const name = text.match(/S\d+/)[0];
        cy.signInAs("sales");
        return call("sale.order", "search_read", [[["name", "=", name]]], { fields: ["name", "order_status"] });
      })
      .then(([submitted]) => {
        expect(submitted.order_status).to.equal("submitted");
        const order = { model: "sale.order", id: submitted.id };
        cy.visit("/odoo/unclaimed-orders");
        cy.contains(".o_data_row", submitted.name).find("button[name=action_claim]").click();
        cy.contains(".o_data_row", submitted.name).should("not.exist");

        cy.openRecord(order);
        openTab("samples");
        cy.get(".o_field_widget[name=sample_ids] .o_field_x2many_list_row_add button").click();
        cy.get(".o_selected_row .o_field_widget[name=customer_sample_name] input").type(sampleName);
        pick("sample_type_id", "Nước đóng chai");
        choose("physical_state", "Lỏng");
        save();
        openTab("order_lines");
        cy.get(".o_field_widget[name=order_line] .o_data_row td[name=sample_id]").first().click();
        pick("sample_id", sampleName);
        openTab("payment");
        choose("advance_method", "Trực tuyến");
        choose("advance_mode", "Phần trăm");
        cy.get(".o_field_widget[name=advance_value] input").clear().type("30");
        cy.sendRecord("action_send_quotation");
        cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");
        cy.readRecord(order, ["invoice_ids"]).its("invoice_ids").should("have.length", 1);
        latestQuotation(order.id).then((quotation) => {
          expect(quotation.status).to.equal("sent");
          const invoice = quotation.advance_invoice_id[0];
          cy.signInAs("customer");
          cy.visit(`/my/invoices/${invoice}`);
          cy.get("button[name=method][value=payos]").click();
          cy.get("#payos-pending").should("be.visible");
        });
      });

    orderAt("accepted").then((paid) => {
      cy.signInAs("sales");
      cy.openRecord(paid);
      cy.get(".o_statusbar_buttons button[name=action_confirm_order]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_request_approval]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").should("exist");
      cy.signInAs("head_of_sales");
      cy.openRecord(paid);
      cy.signRecord();
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]:visible").should("exist");
      cy.readRecord(paid, ["order_status", "approval_status", "test_request_id", "sample_ids"]).then((read) => {
        expect(read.order_status).to.equal("confirmed");
        expect(read.approval_status).to.equal("approved");
        call("medilab.test.request", "read", [[read.test_request_id[0]], ["status", "sample_ids"]]).then(([request]) =>
          expect(request.sample_ids).to.have.length(read.sample_ids.length),
        );
      });
    });
  });

  it("TC-WF01-A1 lets sales create the order for a customer who called", () => {
    cy.signInAs("sales");
    cy.visit("/odoo/lab-orders");
    cy.get(".o_list_button_add").click();
    pick("customer_id", "Công ty TNHH Nước Uống Sạch");
    pick("partner_id", "Phạm Thị Hoa");
    cy.get(".o_field_widget[name=order_line] .o_field_x2many_list_row_add button").first().click();
    cy.get(".o_selected_row td[name=product_and_description] textarea").type("Lead (Pb)");
    cy.contains(".o-autocomplete--dropdown-item a", "Lead (Pb)").click();
    cy.get(".o_field_widget[name=order_line] .o_data_row").should("contain", "280.000");
    save();
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
    visitCatalogAsVisitor();
    cy.contains("tr", "Lead (Pb)").find("button[type=submit]").click();
    cy.get("form[action='/cart/submit'] input[name=name]").type("Lê Văn Khách");
    cy.get("form[action='/cart/submit'] input[name=email]").type(email);
    cy.get("form[action='/cart/submit'] button[type=submit]").first().click();
    cy.contains("h1", "Order submitted");
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
    cy.signInAs("customer");
    resolveRecord("sol_demo.demo_sale_order_completed").then((completed) => {
      cy.visit(`/orders/${completed.id}`);
      cy.get("form[action$='/reorder'] button").click();
      cy.location("pathname")
        .should("match", /^\/orders\/\d+$/)
        .and("not.eq", `/orders/${completed.id}`);
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

    cy.signInAs("sales");
    cy.openRecord("sol_demo.demo_order_template_monthly_water");
    cy.get(".o_statusbar_buttons button[name=action_create_order]:visible").click();
    cy.location("pathname")
      .should("match", /sale\.order\/\d+$/)
      .then((path) => cy.readRecord({ model: "sale.order", id: Number(path.split("/").pop()) }, ["order_status", "state", "quotation_ids"]))
      .should((read) => {
        expect(read.state).to.equal("draft");
        expect(read.quotation_ids).to.be.empty;
      });
  });

  it("TC-WF01-A5 lets sales revise a declined quotation and send the version the customer accepts", () => {
    orderAt("sent").then((order) => {
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}/quotation`);
      cy.get("form[action$='/quotation/decline'] textarea[name=reason]").type(REASON);
      cy.get("form[action$='/quotation/decline'] button").click();
      cy.contains("p", `Reason for declining: ${REASON}`);

      cy.signInAs("sales");
      cy.openRecord(order);
      cy.sendRecord("action_send_quotation");
      cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");
      latestQuotation(order.id).its("revision").should("eq", 2);
      payAdvance(order);
      cy.signInAs("sales");
      call("medilab.quotation", "search_read", [[["order_id", "=", order.id]]], { fields: ["revision", "status"], order: "revision" }).should(
        (quotations) => expect(quotations.map((quotation) => quotation.status)).to.deep.equal(["replaced", "accepted"]),
      );
    });
  });

  it("TC-WF01-A6 flags an expired quotation, which sales extends", () => {
    orderAt("sent").then((order) => {
      const yesterday = new Date(Date.now() - 86400000).toISOString().replace("T", " ").slice(0, 19);
      callAs("demo.sales", "sale.order", "write", [[order.id], { payment_deadline: yesterday }]);
      refAs("demo.administrator", "sol_commerce.cron_flag_expired_quotations").then(({ id }) =>
        callAs("demo.administrator", "ir.cron", "method_direct_trigger", [[id]]),
      );
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
      cy.readRecord(order, ["quotation_follow_up"]).its("quotation_follow_up").should("eq", "unpaid");
    });
  });

  it("TC-WF01-A7 lets the Head of Sales send without an advance to a credit customer, whose order goes ahead unpaid", () => {
    orderAt("claimed", { customer: CUSTOMERS.anPhu }).then((order) => {
      cy.signInAs("head_of_sales");
      cy.openRecord(order);
      openTab("payment");
      choose("advance_method", "No advance");
      cy.sendRecord("action_send_quotation");
      cy.get(".o_statusbar_buttons button[name=action_revise_quotation]:visible").should("exist");

      signIn("portal.anphu");
      cy.visit(`/orders/${order.id}/quotation`);
      cy.get("form[action$='/quotation/accept'] button").click();
      cy.contains("Status: Accepted");

      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_confirm_order]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_request_approval]:visible").should("exist");
      cy.readRecord(order, ["payment_status", "test_request_id"]).then(({ payment_status, test_request_id: [id] }) => {
        expect(payment_status).to.equal("not_paid");
        cy.signInAs("sample_delivery_staff");
        cy.openRecord({ model: "medilab.test.request", id });
        cy.get(".o_statusbar_buttons button[name=action_confirm]:visible").click();
        cy.readRecord({ model: "medilab.test.request", id }, ["status"]).its("status").should("not.eq", "draft");
      });
    });
  });

  it("TC-WF01-A9 lets sales withdraw the approval request, change the order and request it again", () => {
    orderAt("requested", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_request_approval]:visible").should("exist");
      cy.get(".o_field_widget[name=expected_result_date] input").clear().type("31/12/2026");
      cy.get(".o_statusbar_buttons button[name=action_request_approval]:visible").click();
      cy.get(".o_statusbar_buttons button[name=action_withdraw]:visible").should("exist");
      cy.readRecord(order, ["approval_status", "expected_result_date"]).should((read) => {
        expect(read.approval_status).to.equal("requested");
        expect(read.expected_result_date).to.equal("2026-12-31");
      });
    });
  });

  it("TC-WF01-E1 refuses to send a quotation with a line not on a sample", () => {
    orderAt("claimed", { sample: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.expectRefusal({
        read: readOrder(order),
        action: () => cy.sendRecord("action_send_quotation"),
        message: "Gán mẫu cho các mục sau trước khi gửi báo giá:",
      });
    });
  });

  it("TC-WF01-E2 refuses a cart submitted without an e-mail address", () => {
    visitCatalogAsVisitor();
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

  it("TC-WF01-E3 does not let the salesperson who requested approval approve the order", () => {
    orderAt("requested", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_sign]").should("not.exist");
      callRefused("sale.order", "action_sign", [[order.id]]).should("eq", "Only people with the role Head of sales can act at this level.");
      callRefused("sale.order", "write", [[order.id], { validity_date: "2099-12-31" }]).should(
        "eq",
        "The document has signatures; withdraw them before changing it.",
      );
      cy.readRecord(order, ["approval_status"]).its("approval_status").should("eq", "requested");
    });
  });

  it("TC-WF01-E4 refuses to send or change the old version of a revised quotation", () => {
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
          "A replaced quotation cannot be sent. Send the current revision instead.",
        );
        callRefused("medilab.quotation", "write", [[replaced], { decline_reason: REASON }]).should("eq", "A replaced quotation cannot be changed.");
      });
    });
  });

  it("TC-WF01-E5 refuses to confirm the test request of an unpaid order without credit", () => {
    orderAt("approved", { advance: false }).then((order) => {
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

  it("TC-WF01-E6 denies another customer the quotation, invoice and result", () => {
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

describe("WF-01 feature acceptance criteria", () => {
  it("TC-F01-01 shows a parameter of a sub-group when the catalog is filtered by its parent group", () => {
    refAs("demo.administrator", "sol_demo.demo_parameter_group_pesticides").then((pesticides) => {
      becomeVisitor();
      cy.visit(`/catalog?group=${pesticides.id}`);
      cy.contains("tr", "Chlorpyrifos").should("be.visible");
      cy.contains("tr", "Lead (Pb)").should("not.exist");
    });
  });

  it("TC-F01-02 gives a record without a code one from its sequence and refuses a code already used", () => {
    const name = `Kim loại vết ${Date.now()}`;
    cy.signInAs("administrator");
    cy.visit("/odoo/parameter-groups");
    cy.get(".o_list_button_add").click();
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

  it("TC-F01-03 refuses to archive a record still in use and lists what uses it", () => {
    cy.signInAs("administrator");
    resolveRecord("sol_demo.demo_parameter_group_pesticides").then((pesticides) => {
      callRefused("medilab.parameter.group", "action_archive", [[pesticides.id]]).should((message) => {
        expect(message).to.contain("This cannot be archived while these records use it:");
        expect(message).to.contain("Organophosphates");
      });
      cy.readRecord(pesticides, ["active"]).its("active").should("eq", true);
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
    cy.contains("tr", "Lead (Pb)").should("be.visible");
    cy.contains("tr", "Cadmium").should("not.exist");
    orderAt("claimed").then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.intercept("POST", "/web/dataset/call_kw/product.*/*search*").as("productSearch");
      cy.get(".o_field_widget[name=order_line] .o_field_x2many_list_row_add button").first().click();
      cy.get(".o_selected_row td[name=product_and_description] textarea").type("Cadmi");
      cy.wait("@productSearch")
        .its("response.body")
        .should((body) => {
          expect(body.error).to.be.undefined;
          expect(JSON.stringify(body.result)).not.to.contain("Cadmium");
        });
    });
  });

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

  it("TC-F05-02 shows a salesperson their orders and the unclaimed queue, and the Head of Sales every order", () => {
    refAs("demo.administrator", "sol_demo.demo_sale_order_history_sales_2_1").then((other) => {
      cy.signInAs("sales");
      callRefused("sale.order", "read", [[other.id], ["name"]]).should("contain", "sale.order");
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

  it("TC-F06-02 keeps a sent quotation's lines unchanged until it is revised", () => {
    orderAt("sent").then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.expectRefusal({
        read: () => call("sale.order.line", "search_read", [[["order_id", "=", order.id]]], { fields: ["price_unit", "discount", "tax_ids"] }),
        action: () => {
          cy.get(".o_field_widget[name=order_line] .o_data_row td[name=price_unit]").first().click();
          cy.get(".o_selected_row .o_field_widget[name=price_unit] input").clear().type("100000");
          cy.get(".o_form_button_save").click();
        },
        message: "Báo giá đã được gửi; hãy sửa đổi báo giá trước khi sửa các dòng hoặc mẫu của đơn hàng.",
      });
    });
  });

  it("TC-F06-03 refuses to send a quotation without lines", () => {
    cy.signInAs("sales");
    refAs("demo.sales", CUSTOMERS.nuocSach.company)
      .then(({ id }) =>
        callAs("demo.sales", "sale.order", "create", [{ customer_id: id, partner_id: id }], { context: { medilab_sales_order: true } }),
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
        cy.get("button[name=method][value=bank_transfer]").click();
        cy.visit(`/my/invoices/${invoice}`);
        cy.get("#medilab_payment_amount").clear().type("10000");
        cy.get("button[name=method][value=bank_transfer]").click();
        callAs("demo.accountant", "account.payment", "search_read", [[["invoice_ids", "in", [invoice]]]], { fields: ["amount", "state"] }).should(
          (payments) => expect(payments.map((payment) => payment.amount)).to.deep.equal([10000]),
        );
      });
    });
  });

  it("TC-F10-02 starts collecting samples only on an approved order", () => {
    orderAt("requested", { advance: false }).then((order) => {
      cy.signInAs("sales");
      cy.openRecord(order);
      cy.get(".o_statusbar_buttons button[name=action_start_sample_collection]").should("not.exist");
      callRefused("sale.order", "action_start_sample_collection", [[order.id]]).should(
        "eq",
        "The order must be approved before the samples are collected.",
      );
    });
  });
});

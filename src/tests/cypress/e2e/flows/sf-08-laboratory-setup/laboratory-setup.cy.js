import { newRecord, openTab, pick, save } from "../../../support/form";
import { call, callAs, resolveRecord } from "../../../support/odoo";
import {
  ADMINISTRATOR,
  BACKUP_PERSON,
  FINAL_LEVEL,
  HEAD_OF_SALES,
  NEW_PARAMETER,
  PURCHASE_CHAIN,
  REGULATION,
  assignedTest,
  catalogProduct,
  claimedOrder,
  clearBackupRoles,
  clearCarts,
  clearNewLimits,
  pricedParameter,
  requestedOrder,
  resetPurchaseChain,
  taxedPackage,
  unique,
} from "./setup";

const BUTTONS = ".o_form_view .o_statusbar_buttons";

// Adds a row to the editable list of a one2many field on the open form, once the row being edited is left.
function addRow(field) {
  const list = `.o_field_widget[name=${field}]`;
  cy.get(".o_notebook .nav-link.active").click();
  cy.get(".o_selected_row").should("not.exist");
  cy.get(list).then(($list) => {
    const rows = $list.find(".o_data_row").length;
    cy.get(`${list} .o_field_x2many_list_row_add button`).first().click();
    cy.get(`${list} .o_data_row`).should("have.length", rows + 1);
  });
}

// Types into a field of the list row being edited.
function typeInRow(field, text) {
  cy.get(`.o_selected_row .o_field_widget[name=${field}] input`).clear().type(text);
}

// An amount as the portal shows it in either language, such as 220,000 or 220.000.
function amount(thousands) {
  return new RegExp(`${thousands}[.,]000`);
}

// The row of the open cart that holds the item.
function cartRow(name) {
  return cy.contains("main tbody tr", name);
}

// The customer adds a catalog item found by its name and lands in the cart.
function addFromCatalog(name) {
  cy.visit(`/catalog?name=${encodeURIComponent(name)}`);
  cy.contains("tr", name).find("button[type=submit]").click();
  cy.location("pathname").should("eq", "/cart");
}

// Chooses a sample type for the first cart line by its label.
function chooseSampleType(label) {
  cy.get("select[name=sample_type_id]")
    .first()
    .find("option")
    .contains(label)
    .invoke("val")
    .then((value) => {
      cy.get("select[name=sample_type_id]").first().select(String(value));
      // The choice submits the form; the reloaded cart shows it chosen.
      cy.get("select[name=sample_type_id]").first().should("have.value", String(value));
      cy.get("select[name=parameter_method_id]").should("exist");
    });
}

// Submits the cart and yields the order number the confirmation shows.
function submitCart() {
  cy.get("form[action='/cart/submit'] button[type=submit]").first().click();
  cy.contains("h1", "Order submitted");
  return cy
    .contains("p", "is in the sales queue.")
    .invoke("text")
    .then((text) => text.match(/S\d+/)[0]);
}

// The lines of an order, as the head of sales reads them.
function orderLines(name) {
  return callAs(HEAD_OF_SALES, "sale.order.line", "search_read", [[["order_id.name", "=", name]]], {
    fields: ["product_id", "price_unit", "linked_line_id"],
  });
}

// Signs the open purchase order and waits for the signature to be saved.
function signOrder() {
  cy.intercept("POST", "/web/dataset/call_button/purchase.order/action_sign").as("sign");
  cy.signRecord();
  cy.wait("@sign");
}

// The levels a document is signed at, oldest first, as the administrator reads them.
function signatures(document) {
  return callAs(
    ADMINISTRATOR,
    "medilab.signature",
    "search_read",
    [
      [
        ["document_model", "=", document.model],
        ["document_id", "=", document.id],
      ],
    ],
    { fields: ["level_name"], order: "id" },
  ).then((rows) => rows.map((row) => row.level_name));
}

// The names of the apps the signed-in user's home menu offers.
function apps() {
  cy.visit("/odoo");
  cy.get(".o_navbar_apps_menu button").click();
  return cy
    .get(".ml_apps_panel .ml_app_tile_name")
    .should("have.length.greaterThan", 0)
    .then(($items) => Cypress._.sortBy([...$items].map((item) => item.innerText.trim())));
}

describe("SF-08 Laboratory setup", () => {
  // M, A2 and A4 change shared demo records; they are put back even when a test fails.
  afterEach(() => {
    clearNewLimits();
    clearBackupRoles();
    resetPurchaseChain();
  });

  it("TC-SF08-M creates a parameter with its way of testing, regulation limit and price, which a customer orders and a tester runs", () => {
    const name = unique(NEW_PARAMETER);
    cy.signInAs("administrator");
    newRecord("/odoo/test-parameters");
    cy.get(".o_field_widget[name=name] input").type(name);
    pick("group_ids", "Heavy metals");
    pick("main_group_id", "Heavy metals");
    openTab("methods");
    addRow("method_ids");
    pick("method_id", "TCVN 7602:2007");
    pick("department_id", "Chemistry");
    save();
    openTab("sample_types");
    addRow("applicability_ids");
    pick("sample_type_id", "Bottled water");
    pick("parameter_method_id", "TCVN 7602:2007");
    pick("unit_id", "mg/L");
    typeInRow("loq", "0.003");
    cy.get(".o_selected_row .o_field_widget[name=is_default] input").check();
    openTab("price");
    addRow("price_ids");
    typeInRow("list_price", "220000");
    pick("tax_id", "VAT 10%");
    save();
    call("medilab.test.parameter", "search_read", [[["name", "=", name]]], { fields: ["code", "sample_type_ids"] }).then(([parameter]) => {
      expect(parameter.code, "code from the sequence").to.match(/^CT\.\d{4}$/);
      expect(parameter.sample_type_ids, "offered on bottled water").to.have.length(1);
      call("medilab.parameter.method.sample.type", "search_read", [[["parameter_id", "=", parameter.id]]], {
        fields: ["sample_type_id", "unit_id", "loq", "is_default"],
      }).should(([applicability]) => {
        expect(applicability.sample_type_id[1]).to.equal("Bottled water");
        expect(applicability.unit_id[1]).to.equal("mg/L");
        expect(applicability.loq).to.equal(0.003);
        expect(applicability.is_default, "default way").to.be.true;
      });

      // The regulation of bottled water gets a limit for the new parameter.
      cy.openRecord(REGULATION);
      addRow("limit_ids");
      pick("parameter_id", name);
      pick("sample_type_id", "Bottled water");
      cy.get(".o_selected_row .o_field_widget[name=max_set] input").check();
      typeInRow("max_value", "0.01");
      pick("unit_id", "mg/L");
      save();
      call("medilab.regulation.limit", "search_read", [[["parameter_id", "=", parameter.id]]], {
        fields: ["regulation_id", "sample_type_id", "max_value", "unit_id"],
      }).should(([limit]) => {
        expect(limit.regulation_id[1]).to.equal("QCVN 6-1:2010/BYT");
        expect(limit.sample_type_id[1]).to.equal("Bottled water");
        expect(limit.max_value).to.equal(0.01);
        expect(limit.unit_id[1]).to.equal("mg/L");
      });

      clearCarts();
      cy.signInAs("customer");
      addFromCatalog(name);
      cartRow(name).invoke("text").should("match", amount(220));
      chooseSampleType(/Bottled water|Nước đóng chai/);
      cy.get("select[name=parameter_method_id]").first().find("option:selected").should("contain", "TCVN 7602:2007");
      submitCart().then((order) => orderLines(order).its("0.price_unit").should("eq", 220000));

      assignedTest(parameter.id).then((test) => {
        cy.signInAs("tester");
        cy.openRecord(test);
        cy.get(`${BUTTONS} button[name=action_enter_result]:visible`).click();
        cy.get(".o_field_widget[name=value] input").clear().type("0.004");
        // The limit comes from the regulation of bottled water, and the tester concludes against it.
        cy.get(".o_field_widget[name=limit_max]").should("contain", "0.01");
        cy.get(".o_field_widget[name=conclusion] input[data-value=pass]").check();
        save();
        cy.signRecord();
        cy.contains(".o_statusbar_status .o_arrow_button_current", "Awaiting Approval");
        call("medilab.test.result", "search_read", [[["sample_test_id", "=", test.id]]], {
          fields: ["value", "unit_id", "limit_max", "limit_unit_id", "conclusion", "status"],
        }).should(([result]) => {
          expect(result.value).to.equal(0.004);
          expect(result.unit_id[1]).to.equal("mg/L");
          expect(result.limit_max, "limit from the regulation").to.equal(0.01);
          expect(result.limit_unit_id[1]).to.equal("mg/L");
          expect(result.conclusion).to.equal("pass");
          expect(result.status).to.equal("requested");
        });
      });
    });
  });

  it("TC-SF08-A1 creates a service package that the customer orders whole at its own price", () => {
    const name = unique("Nước uống cơ bản");
    cy.signInAs("administrator");
    newRecord("/odoo/service-packages");
    cy.get(".o_field_widget[name=name] input").type(name);
    cy.get(".o_field_widget[name=code] input").type(unique("GOI").replace(" ", "-"));
    pick("tax_id", "VAT 10%");
    cy.get(".o_field_widget[name=list_price] input").clear().type("150000");
    openTab("parameters");
    addRow("line_ids");
    pick("parameter_id", "pH");
    addRow("line_ids");
    pick("parameter_id", "Coliforms");
    save();
    cy.get(".o_field_widget[name=parts_price]").invoke("text").should("match", amount(170));

    clearCarts();
    cy.signInAs("customer");
    addFromCatalog(name);
    cy.get("form[action='/cart/line']").should("have.length", 1);
    cartRow(name).invoke("text").should("match", amount(150));
    cy.contains("tfoot tr", "Total excluding VAT").invoke("text").should("match", amount(150));
    chooseSampleType(/Bottled water|Nước đóng chai/);
    submitCart().then((order) =>
      orderLines(order).should((lines) => {
        const packageLine = lines.find((line) => !line.linked_line_id);
        const parts = lines.filter((line) => line.linked_line_id);
        expect(packageLine.product_id[1]).to.contain(name);
        expect(packageLine.price_unit, "the package's own price").to.equal(150000);
        expect(parts.map((part) => part.product_id[1]).sort()).to.deep.equal(["Coliforms", "pH"]);
        parts.forEach((part) => expect(part.price_unit, `${part.product_id[1]} priced in the package`).to.equal(0));
      }),
    );
  });

  it("TC-SF08-A2 gives a person a role, whose menus they then see and no others", () => {
    clearBackupRoles();
    cy.signInAs("storekeeper");
    apps().then((storekeeperApps) => {
      cy.signInAs("backup_signer");
      apps().should("not.include", "Inventory");

      cy.signInAs("administrator");
      cy.openRecord(BACKUP_PERSON);
      openTab("roles");
      cy.get(".o_field_widget[name=role_ids] .o_field_x2many_list_row_add button").click();
      cy.get(".modal:visible").within(() => {
        cy.get(".o_searchview_input").type("Storekeeper{enter}");
        cy.contains(".o_data_row", "Storekeeper").find("td.o_data_cell").first().click();
      });
      cy.get(".modal").should("not.exist");
      save();
      cy.contains(".o_field_widget[name=role_ids] .o_data_row", "Storekeeper");

      cy.signInAs("backup_signer");
      apps().should("deep.equal", storekeeperApps);
    });
  });

  it("TC-SF08-A3 changes a VAT rate from a date, and a quotation dated after it uses the new rate", () => {
    const totals = () => cy.get(".o_field_widget[name=tax_totals]");
    const lineTaxes = () => cy.get(".o_field_widget[name=product_line_ids] .o_data_row td[name=tax_ids]").first();
    taxedPackage().then(({ tax, product }) => {
      cy.signInAs("administrator");
      cy.openRecord({ model: "medilab.tax", id: tax });
      openTab("rates");
      cy.get(".o_field_widget[name=rate_ids] .o_data_row td[name=valid_until]").first().click();
      typeInRow("valid_until", "12/31/2025{enter}");
      addRow("rate_ids");
      typeInRow("rate", "8");
      typeInRow("valid_from", "01/01/2026{enter}");
      save();
      callAs(ADMINISTRATOR, "medilab.tax.rate", "search_read", [[["tax_id", "=", tax]]], {
        fields: ["rate", "valid_from", "valid_until"],
        order: "valid_from",
      }).should((rates) => {
        expect(rates.map(({ id, ...period }) => period)).to.deep.equal([
          { rate: 10, valid_from: "2020-01-01", valid_until: "2025-12-31" },
          { rate: 8, valid_from: "2026-01-01", valid_until: false },
        ]);
      });

      claimedOrder(product).then((order) => {
        cy.signInAs("sales");
        call("sale.order", "write", [[order.id], { date_order: "2025-12-31 09:00:00" }]);
        cy.openRecord(order);
        openTab("order_lines");
        cy.get(".o_field_widget[name=product_line_ids] .o_data_row").first().should("contain", "280.000");
        lineTaxes().should("contain", "10%");
        totals().should("contain", "28.000").and("contain", "308.000");

        call("sale.order", "write", [[order.id], { date_order: "2026-01-01 09:00:00" }]);
        cy.reload();
        openTab("order_lines");
        lineTaxes().should("contain", "8%");
        totals().should("contain", "22.400").and("contain", "302.400");
      });
    });
  });

  it("TC-SF08-A4 sets the approval chain of a document type, whose documents are then signed level by level", () => {
    resetPurchaseChain();
    cy.signInAs("administrator");
    cy.openRecord(PURCHASE_CHAIN);
    openTab("levels");
    addRow("level_ids");
    typeInRow("sequence", "30");
    typeInRow("name", FINAL_LEVEL);
    pick("role_id", "Administrator");
    save();
    cy.contains(".o_field_widget[name=level_ids] .o_data_row", FINAL_LEVEL);

    requestedOrder().then((order) => {
      cy.signInAs("lab_head");
      cy.openRecord(order);
      signOrder();
      // The lab head's level is signed, and the order still waits for the new level.
      signatures(order).should("deep.equal", ["Storekeeper", "Lab head"]);
      cy.readRecord(order, ["approval_status"]).its("approval_status").should("eq", "requested");

      cy.signInAs("administrator");
      cy.openRecord(order);
      signOrder();
      cy.readRecord(order, ["approval_status"]).its("approval_status").should("eq", "approved");
      signatures(order).should("deep.equal", ["Storekeeper", "Lab head", FINAL_LEVEL]);
    });
  });

  it("TC-SF08-E1 refuses adding to the cart a parameter that has no price", () => {
    clearCarts();
    pricedParameter(unique("Mercury (Hg)")).then((parameter) => {
      cy.signInAs("customer");
      cy.visit(`/catalog?name=${encodeURIComponent(parameter.name)}`);
      cy.contains("tr", parameter.name).invoke("text").should("match", amount(190));
      // The administrator withdraws the price while the customer has the catalog open.
      callAs(ADMINISTRATOR, "medilab.parameter.price", "search", [[["parameter_id", "=", parameter.id]]]).then((prices) =>
        callAs(ADMINISTRATOR, "medilab.parameter.price", "action_archive", [prices]),
      );
      cy.expectRefusal({
        read: () => callAs(HEAD_OF_SALES, "sale.order.line", "search_count", [[["product_id.parameter_id", "=", parameter.id]]]),
        action: () => cy.contains("tr", parameter.name).find("button[type=submit]").click(),
        message: "This item is not in the catalog.",
        messageSelector: "main .text-danger",
      });
      cy.location("pathname").should("eq", "/catalog");
      cy.visit(`/catalog?name=${encodeURIComponent(parameter.name)}`);
      cy.contains("tr", parameter.name).should("not.exist");
      // A parameter that never had a price is not offered either.
      cy.visit("/catalog?name=Chromium");
      cy.contains("tr", "Chromium (VI)").should("not.exist");
      catalogProduct("parameter_id", parameter.id).then((product) =>
        callAs(ADMINISTRATOR, "product.template", "read", [[product], ["sale_ok"]], { context: { active_test: false } })
          .its("0.sale_ok")
          .should("eq", false),
      );
    });
  });

  it("TC-SF08-E2 refuses archiving a record still in use and lists what uses it", () => {
    cy.signInAs("administrator");
    resolveRecord("sol_demo.demo_measurement_unit_mg_l").then((unit) => {
      cy.visit("/odoo/measurement-units");
      cy.contains(".o_data_row", "mg/L").find(".o_list_record_selector input").check();
      cy.expectRefusal({
        read: () => cy.readRecord(unit, ["active", "write_date"]),
        action: () => {
          cy.contains(".o_control_panel button", "Actions").click();
          cy.contains(".o-dropdown-item", "Archive").click();
          cy.get(".modal:visible .modal-footer .btn-primary").click();
        },
        message: "This cannot be archived while these records use it:",
      });
      cy.get(".o_error_dialog").should("contain", "Lead (Pb)").and("contain", "Bottled water");
    });
  });

  it("TC-SF08-E3 refuses a code that already exists", () => {
    const name = unique("Antimony (Sb)");
    const read = () =>
      call("medilab.test.parameter", "search_read", [["|", ["code", "=", "CT.0001"], ["name", "=", name]]], {
        fields: ["name", "write_date"],
        context: { active_test: false },
      });
    cy.signInAs("administrator");
    newRecord("/odoo/test-parameters");
    cy.get(".o_field_widget[name=name] input").type(name);
    cy.get(".o_field_widget[name=code] input").type("CT.0001");
    pick("group_ids", "Heavy metals");
    pick("main_group_id", "Heavy metals");
    cy.expectRefusal({
      read,
      action: () => cy.get(".o_form_button_save").click(),
      message: "The code of a test parameter must be unique.",
    });
  });
});

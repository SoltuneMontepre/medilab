import { callAs, randomId, refAs } from "../../../support/odoo";

export const ADMINISTRATOR = "demo.administrator";
const SALES = "demo.sales";
export const HEAD_OF_SALES = "demo.head_of_sales";
const RECEPTION = "demo.sample_delivery_staff";
const HEAD = "demo.head_of_department";
const STOREKEEPER = "demo.storekeeper";

// The business demo.customer orders for, and the contact its orders name.
const COMPANY = "sol_demo.demo_res_partner_nuoc_sach";
const CONTACT = "sol_demo.demo_res_partner_hoa";

export const PURCHASE_CHAIN = "sol_demo.demo_approval_chain_purchase_order_signing";
export const BACKUP_PERSON = "sol_demo.demo_person_backup_signer";
export const REGULATION = "sol_demo.demo_regulation_qcvn_6_1";
// The name of the parameter the main path creates, before its unique suffix.
export const NEW_PARAMETER = "Arsenic (As)";
// The level the administrator adds to the purchase order chain.
export const FINAL_LEVEL = "Final approval";

// A text no earlier run used, so a test finds its own records.
export function unique(text) {
  return `${text} ${randomId().slice(0, 8)}`;
}

function ref(xmlId) {
  return refAs(ADMINISTRATOR, xmlId).then(({ id }) => id);
}

// Cancels the drafts demo.customer left on the portal, which would otherwise become the cart.
export function clearCarts() {
  return refAs(HEAD_OF_SALES, COMPANY)
    .then(({ id }) =>
      callAs(HEAD_OF_SALES, "sale.order", "search", [
        [
          ["customer_id", "=", id],
          ["order_status", "=", "draft"],
          ["source", "=", "portal"],
        ],
      ]),
    )
    .then((ids) => ids.length && callAs(HEAD_OF_SALES, "sale.order", "action_sales_cancel", [ids]));
}

// The catalog product of a parameter or a package, as the portal posts it.
export function catalogProduct(field, id) {
  return callAs(ADMINISTRATOR, "product.template", "search", [[[field, "=", id]]], { context: { active_test: false } }).then(([product]) => product);
}

// A heavy metal tested by Chemistry on bottled water in mg/L, with the given price at VAT 10%. Yields `{ id, name, price }`.
export function pricedParameter(name) {
  const ids = {};
  ref("sol_demo.demo_parameter_group_heavy_metals").then((id) => (ids.group = id));
  ref("sol_demo.demo_hr_department_chemistry").then((id) => (ids.department = id));
  ref("sol_demo.demo_sample_type_bottled_water").then((id) => (ids.water = id));
  ref("sol_demo.demo_measurement_unit_mg_l").then((id) => (ids.unit = id));
  ref("sol_demo.demo_tax_vat10").then((id) => (ids.tax = id));
  callAs(ADMINISTRATOR, "medilab.testing.method", "search", [[["code", "=", "TCVN 7602:2007"]]]).then(([id]) => (ids.method = id));
  return cy
    .then(() =>
      callAs(ADMINISTRATOR, "medilab.test.parameter", "create", [
        {
          name,
          group_ids: [[6, 0, [ids.group]]],
          main_group_id: ids.group,
          method_ids: [[0, 0, { method_id: ids.method, department_id: ids.department }]],
        },
      ]),
    )
    .then((id) => {
      ids.parameter = id;
      return callAs(ADMINISTRATOR, "medilab.parameter.method", "search", [[["parameter_id", "=", id]]]);
    })
    .then(([way]) => {
      callAs(ADMINISTRATOR, "medilab.test.parameter", "write", [
        [ids.parameter],
        { applicability_ids: [[0, 0, { parameter_method_id: way, sample_type_id: ids.water, unit_id: ids.unit, is_default: true }]] },
      ]);
      return callAs(ADMINISTRATOR, "medilab.parameter.price", "create", [{ parameter_id: ids.parameter, list_price: 190000, tax_id: ids.tax }]);
    })
    .then(() => ({ id: ids.parameter, name, price: 190000 }));
}

// A confirmed request of Nước Uống Sạch with one bottled water sample compared with QCVN 6-1:2010/BYT and tested for
// the parameter, received and assigned to the tester. Receiving and assigning belong to WF-02 and WF-03. Yields the
// sample test as `{ model, id }`.
export function assignedTest(parameterId) {
  const ids = {};
  refAs(RECEPTION, "sol_demo.demo_customer_nuoc_sach").then(({ id }) => (ids.customer = id));
  refAs(RECEPTION, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (ids.water = id));
  refAs(RECEPTION, REGULATION).then(({ id }) => (ids.regulation = id));
  refAs(HEAD, "sol_demo.demo_person_tester").then(({ id }) => (ids.tester = id));
  return cy
    .then(() =>
      callAs(RECEPTION, "medilab.test.request", "create", [
        {
          customer_id: ids.customer,
          sample_ids: [
            [
              0,
              0,
              {
                customer_sample_name: unique("Nước uống đóng chai"),
                sample_type_id: ids.water,
                physical_state: "liquid",
                regulation_id: ids.regulation,
                test_ids: [[0, 0, { parameter_id: parameterId }]],
              },
            ],
          ],
        },
      ]),
    )
    .then((request) => {
      callAs(RECEPTION, "medilab.test.request", "action_confirm", [[request]]);
      return callAs(RECEPTION, "medilab.sample", "search_read", [[["request_id", "=", request]]], { fields: ["test_ids"] });
    })
    .then(([sample]) => {
      ids.test = sample.test_ids[0];
      callAs(RECEPTION, "medilab.sample", "action_receive", [[sample.id], "2 chai", "good"]);
      return callAs(HEAD, "medilab.task", "search", [
        [
          ["document_model", "=", "medilab.sample.test"],
          ["document_id", "=", ids.test],
        ],
      ]);
    })
    .then((tasks) => {
      const context = { active_ids: tasks };
      return callAs(HEAD, "medilab.task.reassign", "create", [{ assignee_id: ids.tester }], { context }).then((wizard) =>
        callAs(HEAD, "medilab.task.reassign", "action_confirm", [[wizard]], { context }),
      );
    })
    .then(() => ({ model: "medilab.sample.test", id: ids.test }));
}

// A tax of 10% since 2020 and a package of Lead at 280,000 taxed with it. Yields `{ tax, package, product }` ids.
export function taxedPackage() {
  const ids = {};
  ref("sol_demo.demo_test_parameter_lead").then((id) => (ids.lead = id));
  return cy
    .then(() =>
      callAs(ADMINISTRATOR, "medilab.tax", "create", [
        { code: unique("VAT").replace(" ", "-"), name: unique("VAT"), rate_ids: [[0, 0, { rate: 10, valid_from: "2020-01-01" }]] },
      ]),
    )
    .then((tax) => {
      ids.tax = tax;
      return callAs(ADMINISTRATOR, "medilab.service.package", "create", [
        {
          code: unique("PB").replace(" ", "-"),
          name: unique("Lead check"),
          list_price: 280000,
          tax_id: tax,
          line_ids: [[0, 0, { parameter_id: ids.lead }]],
        },
      ]);
    })
    .then((pkg) => {
      ids.package = pkg;
      return callAs(ADMINISTRATOR, "product.product", "search", [[["service_package_id", "=", pkg]]]);
    })
    .then(([product]) => ({ tax: ids.tax, package: ids.package, product }));
}

// A portal order of demo.customer, claimed by demo.sales, who adds the product to it; not quoted yet. Yields `{ model, id }`.
export function claimedOrder(product) {
  const ids = {};
  refAs(SALES, COMPANY).then(({ id }) => (ids.company = id));
  refAs(SALES, CONTACT).then(({ id }) => (ids.contact = id));
  return cy
    .then(() =>
      callAs(SALES, "sale.order", "create", [
        {
          customer_id: ids.company,
          partner_id: ids.contact,
          source: "portal",
          order_status: "submitted",
        },
      ]),
    )
    .then((id) => {
      callAs(SALES, "sale.order", "action_claim", [[id]]);
      return callAs(SALES, "sale.order", "write", [[id], { order_line: [[0, 0, { product_id: product, product_uom_qty: 1 }]] }]).then(() => ({
        model: "sale.order",
        id,
      }));
    });
}

// Removes the level an earlier run added to the purchase order chain; a level that orders signed at is archived.
export function resetPurchaseChain() {
  return ref(PURCHASE_CHAIN)
    .then((chain) =>
      callAs(ADMINISTRATOR, "medilab.approval.level", "search", [
        [
          ["chain_id", "=", chain],
          ["name", "=", FINAL_LEVEL],
        ],
      ]),
    )
    .then((levels) => levels.length && callAs(ADMINISTRATOR, "medilab.approval.level", "unlink", [levels]));
}

// A purchase order of sodium chloride the storekeeper sent for approval, signing the first level. Yields `{ model, id }`.
export function requestedOrder() {
  const ids = {};
  refAs(STOREKEEPER, "sol_demo.demo_res_partner_vietnam_chemicals").then(({ id }) => (ids.supplier = id));
  refAs(STOREKEEPER, "sol_demo.demo_hr_department_chemistry").then(({ id }) => (ids.department = id));
  refAs(STOREKEEPER, "sol_demo.demo_product_product_sodium_chloride").then(({ id }) => (ids.item = id));
  return cy
    .then(() =>
      callAs(STOREKEEPER, "purchase.order", "create", [
        {
          partner_id: ids.supplier,
          department_id: ids.department,
          order_line: [[0, 0, { product_id: ids.item, product_qty: 500, price_unit: 380 }]],
        },
      ]),
    )
    .then((id) => {
      return callAs(STOREKEEPER, "purchase.order", "action_request_approval", [[id]]).then(() => ({ model: "purchase.order", id }));
    });
}

// Takes from the backup signer every role an earlier run or another spec gave, permanent or until a date.
export function clearBackupRoles() {
  return ref(BACKUP_PERSON).then((person) => {
    callAs(ADMINISTRATOR, "medilab.person", "write", [[person], { role_ids: [[5, 0, 0]] }]);
    return callAs(ADMINISTRATOR, "medilab.role.grant", "search", [[["person_id", "=", person]]]).then(
      (grants) => grants.length && callAs(ADMINISTRATOR, "medilab.role.grant", "unlink", [grants]),
    );
  });
}

// Removes the limits the main path added to the regulation of bottled water.
export function clearNewLimits() {
  return ref(REGULATION)
    .then((regulation) =>
      callAs(ADMINISTRATOR, "medilab.regulation.limit", "search", [
        [
          ["regulation_id", "=", regulation],
          ["parameter_id.name", "=like", `${NEW_PARAMETER} %`],
        ],
      ]),
    )
    .then((limits) => limits.length && callAs(ADMINISTRATOR, "medilab.regulation.limit", "unlink", [limits]));
}

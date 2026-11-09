import { callAs, callRefused, randomId, refAs } from "../../../../support/odoo";
import { pick, save } from "../../../../support/form";

const ADMINISTRATOR = "demo.administrator";
const SALES = "demo.sales";

function ref(xmlId) {
  return refAs(ADMINISTRATOR, xmlId).then(({ id }) => id);
}

// A regulation on food that limits lead on bottled water and on cabbage, each with its own value, and not on lettuce.
function leadRegulation(code) {
  return ref("sol_demo.demo_sample_type_food").then((foodId) =>
    ref("sol_demo.demo_test_parameter_lead").then((leadId) =>
      ref("sol_demo.demo_sample_type_bottled_water").then((waterId) =>
        ref("sol_demo.demo_sample_type_cabbage").then((cabbageId) =>
          ref("sol_demo.demo_measurement_unit_mg_l").then((mgLId) =>
            ref("sol_demo.demo_measurement_unit_mg_kg").then((mgKgId) =>
              callAs(ADMINISTRATOR, "medilab.regulation", "create", [
                {
                  code,
                  name: "Heavy metals in food",
                  sample_type_ids: [[6, 0, [foodId]]],
                  limit_ids: [
                    [0, 0, { parameter_id: leadId, sample_type_id: waterId, unit_id: mgLId, max_set: true, max_value: 0.01 }],
                    [0, 0, { parameter_id: leadId, sample_type_id: cabbageId, unit_id: mgKgId, max_set: true, max_value: 0.3 }],
                  ],
                },
              ]).then((id) => ({ id, leadId, cabbageId })),
            ),
          ),
        ),
      ),
    ),
  );
}

// A bottled water sample on a new claimed quotation of sales.
function bottledWaterSample() {
  return refAs(SALES, "sol_demo.demo_res_partner_nuoc_sach").then(({ id: customerId }) =>
    refAs(SALES, "sol_demo.demo_res_partner_hoa").then(({ id: contactId }) =>
      refAs(SALES, "sol_demo.demo_sample_type_bottled_water").then(({ id: waterId }) =>
        callAs(SALES, "sale.order", "create", [
          { customer_id: customerId, partner_id: contactId, source: "portal", order_status: "submitted" },
        ]).then((orderId) =>
          callAs(SALES, "sale.order", "action_claim", [[orderId]]).then(() =>
            callAs(SALES, "medilab.order.sample", "create", [
              { order_id: orderId, customer_sample_name: "Lavie 1 L", sample_type_id: waterId, physical_state: "liquid" },
            ]),
          ),
        ),
      ),
    ),
  );
}

function limits(regulationId) {
  return callAs(ADMINISTRATOR, "medilab.regulation.limit", "search_read", [[["regulation_id", "=", regulationId]]], {
    fields: ["sample_type_id", "max_value", "unit_id"],
  });
}

describe("Regulation limits per sample type", () => {
  it("TC-F410: a covered type without its own limit is missing → adding its row and a limit saves it", () => {
    const code = `QCVN TEST ${randomId().slice(0, 8)}`;
    leadRegulation(code).then(({ id, leadId, cabbageId }) => {
      cy.signInAs("administrator");
      cy.openRecord({ model: "medilab.regulation", id });
      // Lettuce offers lead and is in the scope through Food, but never takes the cabbage limit.
      cy.contains(".alert-warning", "Lettuce").should("be.visible");

      pick("add_sample_type_ids", "Lettuce");
      cy.contains(".o_field_widget[name=limit_ids] .o_data_row", "Lettuce").as("lettuce");
      cy.get("@lettuce").should("contain", "mg/kg");
      // The prepared row is a form edit until it is saved.
      limits(id).its("length").should("equal", 2);

      cy.get("@lettuce").find("td[name=sample_type_id]").click();
      cy.get(".o_selected_row .o_field_widget[name=max_set] input").check();
      cy.get(".o_selected_row .o_field_widget[name=max_value] input").clear().type("0.2");
      save();
      cy.get(".alert-warning").should("not.exist");

      limits(id).then((rows) => {
        const values = Object.fromEntries(rows.map((row) => [row.sample_type_id[1], row.max_value]));
        expect(values, "limit per sample type").to.deep.equal({ "Bottled water": 0.01, Cabbage: 0.3, Lettuce: 0.2 });
      });
      callRefused("medilab.regulation.limit", "create", [
        [{ regulation_id: id, parameter_id: leadId, sample_type_id: cabbageId, limit_text: "Not detected" }],
      ]).should("not.be.empty");
    });
  });

  it("TC-F410: sales cannot choose a regulation that is no longer in force", () => {
    bottledWaterSample().then((sampleId) =>
      ref("sol_demo.demo_regulation_qcvn_01_2009").then((expiredId) => {
        cy.signInAs("sales");
        callRefused("medilab.order.sample", "write", [[sampleId], { regulation_id: expiredId }]).should(
          "contain",
          "QCVN 01:2009/BYT",
        );
      }),
    );
  });
});

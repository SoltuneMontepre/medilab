import { callAs, callRefused, refAs } from "../../../../support/odoo";
import { search } from "../../../../support/form";
import { ADMIN, draftReport } from "../../../flows/wf-06-report-release/setup";

describe("Audit trail (F-51)", () => {
  it("TC-F51-01 records who changed a price, when, and its old and new value", () => {
    refAs(ADMIN, "sol_demo.demo_parameter_price_lead").then((price) =>
      refAs(ADMIN, "sol_demo.demo_res_users_administrator").then((administrator) =>
        callAs(ADMIN, "res.users", "read", [[administrator.id], ["name"]]).then(([{ name }]) => {
          cy.signInAs("administrator");
          cy.openRecord(price);
          cy.get("button[name=action_open_audit_history]").click();
          cy.contains(".o_data_row", "Edit").should("contain", name);
          callAs(
            ADMIN,
            "medilab.audit.entry",
            "search_read",
            [
              [
                ["document_model", "=", "medilab.parameter.price"],
                ["document_id", "=", price.id],
                ["action", "=", "edit"],
              ],
            ],
            { fields: ["user_id", "create_date", "change_ids"] },
          ).then((entries) => {
            expect(entries[0].user_id[1], "who").to.equal(name);
            expect(entries[0].create_date, "when").to.be.a("string");
            callAs(ADMIN, "medilab.audit.change", "read", [
              entries.flatMap((entry) => entry.change_ids),
              ["field_name", "old_value", "new_value"],
            ]).should((changes) =>
              expect(changes.map((change) => [change.field_name, change.old_value, change.new_value])).to.deep.include([
                "list_price",
                "250000.0",
                "280000.0",
              ]),
            );
          });
        }),
      ),
    );
  });

  it("TC-F51-02 includes a request's samples and sample tests in its history, and masks personal data", () => {
    draftReport().then(({ request }) => {
      callAs(ADMIN, "medilab.test.request", "action_open_audit_history", [[request.id]]).then((action) =>
        callAs(ADMIN, "medilab.audit.entry", "search_read", [action.domain], { fields: ["document_model"] }).should((entries) =>
          expect(entries.map((entry) => entry.document_model)).to.include.members(["medilab.test.request", "medilab.sample", "medilab.sample.test"]),
        ),
      );
      cy.signInAs("administrator");
      cy.openRecord(request);
      cy.get("button[name=action_open_audit_history]").click();
      cy.get(".o_data_row").should("have.length.greaterThan", 2);
    });
    const citizenId = `07908${String(Date.now()).slice(-7)}`;
    refAs(ADMIN, "sol_demo.demo_customer_pham_van_long").then((customer) => {
      callAs(ADMIN, "medilab.customer", "read", [[customer.id], ["citizen_id"]])
        .its("0.citizen_id")
        .as("seeded");
      callAs(ADMIN, "medilab.customer", "write", [[customer.id], { citizen_id: citizenId }]);
      callAs(
        ADMIN,
        "medilab.audit.change",
        "search_read",
        [
          [
            ["entry_id.document_model", "=", "medilab.customer"],
            ["entry_id.document_id", "=", customer.id],
            ["field_name", "=", "citizen_id"],
          ],
        ],
        { fields: ["new_value"], order: "id desc", limit: 1 },
      )
        .its("0.new_value")
        .should("eq", `***${citizenId.slice(-3)}`);
      cy.get("@seeded").then((seeded) => callAs(ADMIN, "medilab.customer", "write", [[customer.id], { citizen_id: seeded }]));
    });
  });

  it("TC-F51-03 lets nobody change or delete an audit entry, administrators included", () => {
    callAs(ADMIN, "medilab.audit.entry", "search", [[]], { limit: 1 }).then(([entry]) => {
      cy.signInAs("administrator");
      callRefused("medilab.audit.entry", "write", [[entry], { note: "Sửa" }]).should("eq", "Audit entries cannot be changed.");
      callRefused("medilab.audit.entry", "unlink", [[entry]]).should("match", /^You are not allowed to delete 'Audit Entry'/);
    });
  });
});

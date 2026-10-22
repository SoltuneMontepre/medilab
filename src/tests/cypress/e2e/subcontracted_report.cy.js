import { call, signIn } from "../support/odoo";

describe("Subcontracted results on the test report", () => {
  it("marks the result a subcontractor tested and explains the mark", () => {
    signIn("demo.lab_head");

    call("ir.model.data", "check_object_reference", ["sol_demo", "demo_test_report_subcontracted"]).then(([, id]) => {
      cy.visit(`/report/html/sol_laboratory.report_test_report/${id}`);
      cy.contains("td", /\(TP\)$/).should("exist");
      cy.contains("(TP) Chỉ tiêu do nhà thầu phụ thực hiện / Tested by a subcontractor").should("be.visible");
    });
  });
});

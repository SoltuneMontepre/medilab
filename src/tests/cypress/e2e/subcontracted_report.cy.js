const PASSWORD = "demo";

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

function call(model, method, args, kwargs = {}) {
  return cy
    .request("POST", `/web/dataset/call_kw/${model}/${method}`, {
      jsonrpc: "2.0",
      method: "call",
      params: { model, method, args, kwargs },
    })
    .then(({ body }) => {
      expect(body.error, JSON.stringify(body.error)).to.be.undefined;
      return body.result;
    });
}

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

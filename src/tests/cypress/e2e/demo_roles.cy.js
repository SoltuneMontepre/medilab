const ROLES = [
  "administrator",
  "sales",
  "sales_2",
  "head_of_sales",
  "accountant",
  "sample_delivery_staff",
  "tester",
  "chemistry_tester",
  "microbiology_tester",
  "head_of_department",
  "lab_head",
  "subcontractor",
  "storekeeper",
  "customer",
  "individual",
  "registered",
  "invited",
  "auditor",
];

describe("Demo role sessions", () => {
  for (const role of ROLES) {
    it(`signs in as ${role}`, () => {
      cy.signInAs(role);
      cy.request("POST", "/web/session/get_session_info", {
        jsonrpc: "2.0",
        method: "call",
        params: {},
      }).its("body.result.username").should("eq", `demo.${role}`);
    });
  }

  it("opens and reads a demo record by its external ID", () => {
    cy.signInAs("head_of_department");
    cy.openRecord("sol_demo.demo_test_result_retest").then(({ model, id }) => {
      expect(model).to.equal("medilab.test.result");
      cy.location("pathname").should("include", `/medilab.test.result/${id}`);
    });
    cy.readRecord("sol_demo.demo_test_result_retest", ["status", "write_date"])
      .should("have.property", "status");
  });
});

describe("Login", () => {
  it("shows the login form", () => {
    cy.visit("/web/login");

    cy.get("input[name=login]").should("be.visible");
    cy.get("input[name=password]").should("be.visible");
  });

  it("rejects a wrong password", () => {
    cy.visit("/web/login");

    cy.get("input[name=login]").type("admin");
    cy.get("input[name=password]").type("wrong-password{enter}");

    cy.contains("Wrong login/password");
  });
});

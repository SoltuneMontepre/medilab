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

    cy.contains("Wrong login/password").should("be.visible");
  });

  describe("Demo sessions", () => {
    beforeEach(() => cy.signInAs("tester"));

    it("signs in as the demo tester", () => {
      cy.get(".o_web_client").should("be.visible");
    });

    it("restores the demo tester session without another login", () => {
      cy.intercept("POST", "/web/login").as("login");
      cy.signInAs("tester");
      cy.get(".o_web_client").should("be.visible");
      cy.get("@login.all").should("have.length", 0);
    });
  });
});

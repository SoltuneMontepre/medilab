const LIST = "/my/notifications";
const NOTICES = "#portal-notifications li";

// demo.registered's address bounced, so no email of these notices left; sol_demo seeds an invoice notice not yet
// opened and a payment receipt already opened.
function noticeLink(subject) {
  return cy.contains(`${NOTICES} a`, subject);
}

describe("Mandatory notices", () => {
  it("TC-F436-01 keeps a mandatory notice in the portal of a customer whose email bounced, and marks it seen once opened", () => {
    cy.signInAs("registered");
    cy.visit(LIST);
    cy.get(NOTICES).should("have.length.at.least", 2);
    noticeLink("Payment receipt").closest("li").should("not.contain", "New");

    noticeLink("Invoice HD-0001").click();
    cy.location("pathname").should("match", /^\/my\/notifications\/\d+$/);
    cy.get("#notification-subject").should("have.text", "Invoice HD-0001");
    cy.get("#notification-body").should("contain", "Invoice HD-0001 is ready in your portal.");

    cy.contains("a", "Back to notifications").click();
    cy.location("pathname").should("eq", LIST);
    noticeLink("Invoice HD-0001").closest("li").should("not.contain", "New");
  });

  it("TC-F436-02 shows a notice only to the contact it was sent to", () => {
    cy.signInAs("registered");
    cy.visit(LIST);
    noticeLink("Invoice HD-0001")
      .invoke("attr", "href")
      .then((href) => {
        cy.signInAs("customer");
        cy.visit(LIST);
        cy.get("body").should("not.contain", "Invoice HD-0001");
        cy.request({ url: href, failOnStatusCode: false }).its("status").should("eq", 404);
      });
  });
});

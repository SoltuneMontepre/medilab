const SWITCHER = "li.o_medilab_language_switcher";
const ACCOUNT_LANGUAGE = "form[action='/my/language']:has(select[name=lang])";

function switchFromHeader(language) {
  cy.get(`${SWITCHER} > a`).click();
  cy.get(`${SWITCHER} .dropdown-menu button`).contains(language).click();
}

function saveOnAccountPage(code) {
  cy.visit("/my/account");
  cy.get(`${ACCOUNT_LANGUAGE} select[name=lang]`).select(code);
  cy.get(`${ACCOUNT_LANGUAGE} button[type=submit]`).click();
  cy.location("pathname").should("eq", "/my/account");
}

describe("Portal language", () => {
  it("lets a customer switch the language from the header and keeps it on their profile", () => {
    cy.signInAs("customer");
    saveOnAccountPage("en_US");

    cy.visit("/orders");
    cy.get(`${SWITCHER} > a`).should("contain.text", "English");
    switchFromHeader("Tiếng Việt");
    cy.location("pathname").should("eq", "/orders");
    cy.get(`${SWITCHER} > a`).should("contain.text", "Tiếng Việt");

    cy.visit("/my/account");
    cy.get(`${ACCOUNT_LANGUAGE} select[name=lang]`).should("have.value", "vi_VN");

    saveOnAccountPage("en_US");
    cy.get(`${SWITCHER} > a`).should("contain.text", "English");
  });

  it("lets a visitor switch the catalog's language", () => {
    cy.visit("/catalog");
    switchFromHeader("Tiếng Việt");
    cy.location("pathname").should("match", /\/catalog$/);
    cy.get(`${SWITCHER} > a`).should("contain.text", "Tiếng Việt");
  });
});

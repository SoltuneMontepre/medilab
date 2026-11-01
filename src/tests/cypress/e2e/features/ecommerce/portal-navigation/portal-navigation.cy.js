const NAVIGATION = "ul.o_medilab_portal_navigation";
const SECTIONS = ["/orders", "/support", "/my/account", "/catalog"];

function expectLinks(hrefs) {
  cy.get(`${NAVIGATION} a`).then(($links) => {
    expect($links.toArray().map((link) => link.getAttribute("href"))).to.deep.equal(hrefs);
  });
}

describe("Portal navigation", () => {
  it("takes a customer to the catalog, their orders, support and their account from the header", () => {
    cy.signInAs("customer");
    cy.visit("/my");
    expectLinks(["/catalog", "/orders", "/support", "/my/account"]);
    cy.get(".o_portal_index_card:not(.d-none) a[href='/support']").should("be.visible");

    for (const href of SECTIONS) {
      cy.get(`${NAVIGATION} a[href='${href}']`).click();
      cy.location("pathname").should("eq", href);
      cy.get(`${NAVIGATION} a.active`).should("have.attr", "href", href).and("have.attr", "aria-current", "page");
    }

    cy.get("select[name=sample_type] option[value='']").should("have.text", "All sample types");
    cy.visit("/my/account");
    cy.contains("main h3", /^Customer$/).should("not.exist");
    cy.get("main a[href='/orders']").should("exist");
  });

  it("shows a visitor only the catalog link, and only in the catalog", () => {
    cy.visit("/catalog");
    expectLinks(["/catalog"]);
    cy.visit("/verify");
    cy.get(NAVIGATION).should("not.exist");
  });
});

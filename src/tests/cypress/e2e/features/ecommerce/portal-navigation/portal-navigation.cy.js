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

  it("filters My orders by status and by order number, and keeps the filters on the order page", () => {
    const rows = "main table tbody tr";
    const filter = () => cy.get("main form[action='/orders'] button[type=submit]").click();
    cy.signInAs("customer");
    cy.visit("/orders");
    cy.get("select[name=status] option[value='']").should("have.text", "All statuses");

    cy.get(`${rows} td:nth-child(3)`)
      .first()
      .invoke("text")
      .then((label) => {
        const status = label.trim();
        cy.get("select[name=status]").select(status);
        filter();
        cy.location("search").should("include", "status=");
        cy.get(`${rows} td:nth-child(3)`).each(($cell) => expect($cell.text().trim()).to.equal(status));
      });

    cy.get(`${rows} td:first-child > a`)
      .first()
      .invoke("text")
      .then((name) => {
        cy.get("input[name=search]").clear().type(name);
        filter();
        cy.get(`${rows} td:first-child > a`).each(($link) => expect($link.text()).to.include(name));
        cy.get(`${rows} td:first-child > a`).first().click();
        cy.location("search").should("include", "search=");
        cy.get("main a:has(i[data-icon='arrow_back'])").click();
        cy.location("pathname").should("eq", "/orders");
        cy.get("input[name=search]").should("have.value", name);
      });

    cy.get("input[name=search]").clear().type("no order has this text");
    filter();
    cy.contains("main p", "No orders match these filters.").find("a").click();
    cy.location("search").should("eq", "");
    cy.get(rows).should("not.have.length", 0);
  });

  it("shows a visitor only the catalog link, and only in the catalog", () => {
    cy.visit("/catalog");
    expectLinks(["/catalog"]);
    cy.visit("/verify");
    cy.get(NAVIGATION).should("not.exist");
  });
});

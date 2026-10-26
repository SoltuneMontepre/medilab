const MESSAGE = "Signing is not allowed.";
const read = () => cy.window().then((win) => win.record);

describe("Browser helper commands", () => {
  let failureHandler;
  let failureObserved;

  function expectFailure(text) {
    failureObserved = false;
    failureHandler = (error) => {
      expect(error.message).to.include(text);
      failureObserved = true;
      return false;
    };
    Cypress.once("fail", failureHandler);
  }

  beforeEach(() => {
    failureHandler = undefined;
    cy.intercept("GET", "/__browser_helpers__", {
      fixture: "browser_helpers.html",
      headers: { "content-type": "text/html" },
    });
    cy.visit("/__browser_helpers__");
  });

  afterEach(() => {
    if (failureHandler) {
      Cypress.off("fail", failureHandler);
      expect(failureObserved, "the refusal check must fail").to.be.true;
    }
  });

  it("signs using the visible form action", () => {
    cy.signRecord();
    read().should((record) => expect(record.status).to.equal("approved"));
  });

  it("sends using the document's action name", () => {
    cy.sendRecord("action_send_quotation");
    read().should((record) => expect(record.status).to.equal("sent"));
  });

  it("rejects with a literal reason and closes the wizard", () => {
    const reason = "Check {enter} against the original measurement.";
    cy.rejectRecord(reason);
    read().should((record) => expect(record).to.deep.equal({ status: "rejected", reason }));
  });

  it("checks the displayed refusal and the unchanged record", () => {
    cy.expectRefusal({
      read,
      action: () => cy.get("#refuse").click(),
      message: MESSAGE,
    });
    read().should((record) => expect(record.status).to.equal("requested"));
  });

  it("fails when the action succeeds", { defaultCommandTimeout: 300 }, () => {
    expectFailure(MESSAGE);
    cy.expectRefusal({ read, action: () => cy.signRecord(), message: MESSAGE });
  });

  it("fails when an error is displayed but the record changes", () => {
    expectFailure("record after refusal");
    cy.expectRefusal({
      read,
      action: () => cy.get("#changed").click(),
      message: MESSAGE,
    });
  });

  it("fails when the displayed refusal has the wrong message", { defaultCommandTimeout: 300 }, () => {
    expectFailure("A different refusal.");
    cy.expectRefusal({
      read,
      action: () => cy.get("#refuse").click(),
      message: "A different refusal.",
    });
  });

  it("rejects a refusal left over from an earlier action", { defaultCommandTimeout: 300 }, () => {
    cy.get("#refuse").click();
    expectFailure("Expected not to find content");
    cy.expectRefusal({ read, action: () => cy.signRecord(), message: MESSAGE });
  });
});

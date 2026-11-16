import { assertNoPriorRefusal, assertRefusalOutcome } from "../support/refusal";

const MESSAGE = "Signing is not allowed.";
const read = () => cy.window().then((win) => win.record);

describe("Browser helper commands", () => {
  beforeEach(() => {
    cy.intercept("GET", "/__browser_helpers__", {
      fixture: "browser_helpers.html",
      headers: { "content-type": "text/html" },
    });
    cy.visit("/__browser_helpers__");
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

  it("fails when the action succeeds", () => {
    const record = { status: "requested", reason: "" };
    expect(() => assertRefusalOutcome({ displayedMessage: "", message: MESSAGE, before: record, after: record })).to.throw();
  });

  it("fails when an error is displayed but the record changes", () => {
    expect(() =>
      assertRefusalOutcome({
        displayedMessage: MESSAGE,
        message: MESSAGE,
        before: { status: "requested", reason: "" },
        after: { status: "approved", reason: "" },
      }),
    ).to.throw("record after refusal");
  });

  it("fails when the displayed refusal has the wrong message", () => {
    expect(() =>
      assertRefusalOutcome({
        displayedMessage: "A different refusal.",
        message: MESSAGE,
        before: { status: "requested", reason: "" },
        after: { status: "requested", reason: "" },
      }),
    ).to.throw("displayed refusal");
  });

  it("rejects a refusal left over from an earlier action", () => {
    expect(() => assertNoPriorRefusal(MESSAGE, MESSAGE)).to.throw("no refusal is left from an earlier action");
  });
});

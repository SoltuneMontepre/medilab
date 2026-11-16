import { callAs, randomId, refAs, signIn } from "../../../../support/odoo";
import { onPhone, signedInPhone } from "../../../../support/mobile";
import { step } from "../../../../support/steps";

const SALES = "demo.sales";
const CUSTOMER = "demo.customer";
const ADMINISTRATOR = "demo.administrator";

// A question demo.customer asks on the portal about no order, so it waits for a salesperson to take it.
function waitingRequest(subject) {
  return callAs(CUSTOMER, "medilab.support.request", "portal_open", [subject, false, "When do we get the results?"]).then(() =>
    callAs(ADMINISTRATOR, "medilab.support.request", "search", [[["subject", "=", subject]]]).its(0),
  );
}

describe("Medilab Mobile support requests on the portal", () => {
  it("TC-F522-A1 shows the customer the answer sales sent from the phone, and notifies them", () => {
    const subject = `Bottled water results ${randomId().slice(0, 8)}`;
    const answer = `Your results are ready on Friday ${randomId().slice(0, 8)}.`;
    step("The customer asks a question on the portal");
    waitingRequest(subject).then((requestId) => {
      step("Sales takes the waiting request on the phone");
      signedInPhone(SALES).then((key) => {
        onPhone(key, "GET", "/support-requests?list=waiting").then(({ status, body }) => {
          expect(status).to.eq(200);
          expect(body.requests.map(({ id }) => id)).to.include(requestId);
        });
        onPhone(key, "POST", `/support-requests/${requestId}/take`).its("body.actions").should("deep.equal", { take: false, answer: true });
        step("Sales answers the request on the phone");
        onPhone(key, "POST", `/support-requests/${requestId}/answer`, { body: answer }, { "Idempotency-Key": randomId() }).then(
          ({ status, body }) => {
            expect(status).to.eq(200);
            expect(body.status).to.eq("answered");
            expect(body.messages.map((message) => message.body)).to.include(answer);
          },
        );
      });

      step("The customer is notified of the answer");
      callAs(ADMINISTRATOR, "mail.message", "search_read", [[["model", "=", "medilab.support.request"], ["res_id", "=", requestId]]], {
        fields: ["notified_partner_ids", "author_id"],
        order: "id desc",
        limit: 1,
      }).then(([message]) =>
        refAs(ADMINISTRATOR, "sol_demo.demo_res_partner_hoa").then(({ id: customerId }) => {
          expect(message.notified_partner_ids, "the customer is notified").to.include(customerId);
        }),
      );

      step("The customer reads the answer on the portal");
      signIn(CUSTOMER);
      cy.visit(`/support/${requestId}`);
      cy.contains("h1", subject);
      cy.contains(".o-mail-Message-body", answer, { includeShadowDom: true }).should("be.visible");
    });
  });
});

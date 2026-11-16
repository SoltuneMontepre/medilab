import { randomId, refAs, signIn } from "../../../../support/odoo";
import { onPhone, signedInPhone } from "../../../../support/phone";

const TESTER = "demo.tester";
const HEAD = "demo.head_of_department";

// The direct conversation of demo.tester and the head of Chemistry, opened on the tester's phone as Discuss opens it.
function directConversation(key) {
  return refAs(TESTER, "sol_demo.demo_res_users_head_of_department").then(({ id: headId }) =>
    onPhone(key, "POST", "/conversations", { person_id: headId }).then(({ status, body }) => {
      expect(status).to.eq(200);
      return cy.wrap(body);
    }),
  );
}

// Reads the conversation on the phone until it lists the text from another person; Discuss shows a message it sends
// before the server has saved it.
function receivedOnPhone(key, conversationId, text, attempts = 10) {
  return onPhone(key, "GET", `/conversations/${conversationId}/messages`).then(({ status, body }) => {
    expect(status, JSON.stringify(body)).to.eq(200);
    if (body.messages.some((message) => message.text === text && !message.mine)) return;
    expect(attempts, `${text} on the phone`).to.be.greaterThan(1);
    cy.wait(500);
    receivedOnPhone(key, conversationId, text, attempts - 1);
  });
}

describe("Medilab Mobile conversations in Discuss", () => {
  it("TC-F521-A1 crosses messages between the phone and Discuss on the web in both directions", () => {
    const fromPhone = `Mẫu bắp cải đã cân xong ${randomId()}`;
    const fromWeb = `Nhận rồi, cảm ơn em ${randomId()}`;
    signedInPhone(TESTER).then((key) =>
      directConversation(key).then((conversation) => {
        onPhone(key, "POST", `/conversations/${conversation.id}/messages`, { text: fromPhone }, { "Idempotency-Key": randomId() })
          .its("status")
          .should("eq", 200);

        signIn(HEAD);
        cy.visit(`/odoo/discuss?active_id=discuss.channel_${conversation.id}`);
        cy.contains(".o-mail-Message", fromPhone).should("be.visible");
        // Discuss sends with Enter.
        cy.get(".o-mail-Composer-input").type(`${fromWeb}{enter}`);
        cy.contains(".o-mail-Message", fromWeb).should("be.visible");

        // A phone calls without the browser's session.
        cy.clearCookies();
        receivedOnPhone(key, conversation.id, fromWeb);
      }),
    );
  });

  it("TC-F521-A2 refuses a customer in a conversation", () => {
    refAs(TESTER, "sol_demo.demo_res_users_customer").then(({ id: customerId }) =>
      signedInPhone(TESTER).then((key) =>
        onPhone(key, "POST", "/conversations", { person_id: customerId }).then(({ status, body }) => {
          expect(status).to.eq(400);
          expect(body.error.code).to.eq("invalid_request");
        }),
      ),
    );
  });

  it("TC-F521-A3 shows a note posted from the phone in the sample's chatter on the web", () => {
    const note = `Lá ngoài còn ướt, cần đồng nhất lại ${randomId()}`;
    refAs(HEAD, "sol_demo.demo_sample_cabbage_received").then(({ id: sampleId }) =>
      signedInPhone(HEAD).then((key) => {
        onPhone(key, "POST", `/documents/medilab.sample/${sampleId}/notes`, { text: note }, { "Idempotency-Key": randomId() })
          .its("body.note")
          .should("eq", true);

        signIn(HEAD);
        cy.visit(`/odoo/medilab.sample/${sampleId}`);
        cy.contains(".o-mail-Message", note).should("be.visible");
      }),
    );
  });
});

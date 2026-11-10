import { openTab, search } from "../../../support/form";
import { becomeVisitor, call, callAs, callRefused, randomId } from "../../../support/odoo";
import { CUSTOMER, OTHER_CUSTOMER, SALES, openRequest, orderIn, rateOrder, unique } from "./setup";

const REQUEST_FIELDS = ["code", "status", "handled_by_id"];
// A 1x1 PNG, the smallest logo the portal accepts.
const LOGO = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

// The head of sales reads every request, taken or not.
const readRequest = (request) => callAs("demo.head_of_sales", request.model, "read", [[request.id], REQUEST_FIELDS]).then(([read]) => read);

// The id of a login's user, read by sales.
function userId(login) {
  return callAs(SALES, "res.users", "search", [[["login", "=", login]]]).then(([id]) => id);
}

// Whether a salesperson's list of support requests holds the request.
function salesSees(login, request) {
  return callAs(login, request.model, "search", [[["id", "=", request.id]]]).then((ids) => ids.length === 1);
}

// A visitor registers a business with a tax code, and yields the login.
function signUp({ name, company, vat }) {
  const login = `${randomId().slice(0, 8)}@sf09.example`;
  const password = randomId();
  cy.visit("/web/signup");
  cy.get("input[name=name]").type(name);
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(password, { log: false });
  cy.get("input[name=confirm_password]").type(password, { log: false });
  cy.get("select[name=customer_type]").select("business");
  cy.get("input[name=company_name]").type(company);
  cy.get("input[name=vat]").type(vat);
  cy.get("input[name=phone]").type("028 3999 1234");
  cy.get("input[name=street]").type("1 Lê Lợi");
  cy.get("input[name=city]").type("Hồ Chí Minh");
  cy.get("form").filter(":has(input[name=confirm_password])").find("button[type=submit]").click();
  cy.location("pathname").should("not.eq", "/web/signup");
  return cy.wrap(login, { log: false });
}

// A tax code no earlier run registered.
function newVat() {
  return `03${String(Date.now()).slice(-8)}`;
}

// Posts a chatter message on the open back-office form.
function reply(text) {
  cy.get(".o-mail-Chatter-sendMessage").click();
  cy.get(".o-mail-Composer-input").type(text);
  cy.get(".o-mail-Composer-send").should("be.enabled").click();
  cy.contains(".o-mail-Message-body", text).should("be.visible");
}

describe("SF-09 Customer support and feedback", () => {
  it("TC-SF09-M answers a support request about an order through the order's salesperson and notifies the customer", () => {
    const subject = unique("When will the results be ready?");
    const answer = unique("The results are ready on Friday.");
    orderIn("confirmed").then((order) => {
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}`);
      cy.get(`main a[href='/support/new?order_id=${order.id}']`).click();
      cy.get("select[name=order_id]").should("have.value", String(order.id));
      cy.get("input[name=subject]").type(subject);
      cy.get("textarea[name=body]").type("We need the lead results before our audit.");
      cy.get("form[action='/support/open'] button[type=submit]").click();
      cy.location("pathname").should("match", /^\/support\/\d+$/);
      cy.contains("main h1", subject);
      cy.contains("main a", order.name);
      cy.location("pathname").then((path) => {
        const request = { model: "medilab.support.request", id: Number(path.split("/").pop()) };
        readRequest(request).then((read) => expect(read.status).to.equal("open"));
        userId(SALES).then((salesId) =>
          readRequest(request).then((read) => expect(read.handled_by_id[0], "handled by the order's salesperson").to.equal(salesId)),
        );
        // The request reaches the salesperson's to-do list.
        callAs(SALES, "medilab.task", "search", [
          [
            ["document_model", "=", request.model],
            ["document_id", "=", request.id],
            ["status", "not in", ["done", "cancelled"]],
          ],
        ]).should("have.length", 1);

        cy.signInAs("sales");
        cy.openRecord(request);
        reply(answer);
        cy.readRecord(request, ["status"]).its("status").should("eq", "answered");
        call(
          "mail.message",
          "search_read",
          [
            [
              ["model", "=", request.model],
              ["res_id", "=", request.id],
              ["body", "ilike", answer],
            ],
          ],
          { fields: ["notified_partner_ids"] },
        ).then(([message]) =>
          call("res.users", "search_read", [[["login", "=", CUSTOMER]]], { fields: ["partner_id"] }).then(([customer]) =>
            expect(message.notified_partner_ids, "customer notified").to.include(customer.partner_id[0]),
          ),
        );
        callAs(SALES, "medilab.task", "search", [
          [
            ["document_model", "=", request.model],
            ["document_id", "=", request.id],
            ["status", "not in", ["done", "cancelled"]],
          ],
        ]).should("have.length", 0);

        cy.signInAs("customer");
        cy.visit(`/support/${request.id}`);
        cy.get("main .badge").should("have.class", "text-bg-info");
        cy.contains(".o-mail-Message-body", answer, { includeShadowDom: true }).should("be.visible");
      });
    });
  });

  it("TC-SF09-A1 shows a support request about no order to every salesperson until one takes it", () => {
    openRequest(unique("Export certificate")).then((request) => {
      salesSees(SALES, request).should("be.true");
      salesSees("demo.sales_2", request).should("be.true");
      readRequest(request).its("handled_by_id").should("be.false");

      cy.signInAs("sales_2");
      cy.visit("/odoo/support-requests");
      readRequest(request).then(({ code }) => {
        search(code);
        cy.contains(".o_data_row", request.subject).find("button[name=action_take]").click();
        cy.contains(".o_data_row", request.subject).find("button[name=action_take]").should("not.exist");
      });

      userId("demo.sales_2").then((id) => readRequest(request).its("handled_by_id.0").should("eq", id));
      salesSees("demo.sales_2", request).should("be.true");
      salesSees(SALES, request).should("be.false");
    });
  });

  it("TC-SF09-A2 registers a customer who keeps their profile and contacts and uploads a logo", () => {
    const company = unique("Công ty Sao Mai");
    const contact = unique("Ngô Thị Lan");
    becomeVisitor();
    signUp({ name: "Đỗ Văn Tài", company, vat: newVat() });

    cy.visit("/my/account");
    cy.contains("main dd", /^KH\./);
    cy.get("main select[name=lang]").select("en_US");
    cy.get("main form[action='/my/language'] button[type=submit]").click();
    cy.get("main select[name=lang]").should("have.value", "en_US");

    cy.get("main a[href='/my/contacts']").click();
    cy.contains("main tr", "Đỗ Văn Tài").find(".badge").should("exist");
    cy.get("main a[href='/my/contacts/new']").click();
    cy.get("input[name=name]").type(contact);
    cy.get("input[name=function]").type("Accountant");
    cy.get("input[name=email]").type("lan@saomai.example");
    cy.get("form[action='/my/contacts/save'] button[type=submit]").click();
    cy.location("pathname").should("eq", "/my/contacts");
    cy.contains("main tr", contact).find("form[action$='/default'] button").click();
    cy.contains("main tr", contact).find(".badge").should("exist");
    cy.contains("main tr", "Đỗ Văn Tài").find(".badge").should("not.exist");

    cy.visit("/my/account");
    cy.get("main img[alt=Logo]").should("not.exist");
    cy.get("main form[action='/my/logo'] input[name=logo]").selectFile({
      contents: Cypress.Buffer.from(LOGO, "base64"),
      fileName: "logo.png",
      mimeType: "image/png",
    });
    cy.get("main form[action='/my/logo'] button[type=submit]").click();
    cy.get("main img[alt=Logo]").should("be.visible");
  });

  it("TC-SF09-A3 invites a customer to the portal and merges a duplicate profile", () => {
    const name = unique("Công ty Hải Đăng");
    const email = `${randomId().slice(0, 8)}@haidang.example`;
    const vat = newVat();
    callAs(SALES, "medilab.customer", "create", [{ name, email, vat }]).then((customerId) => {
      const customer = { model: "medilab.customer", id: customerId };
      // The same business registers itself on the portal with its tax code.
      becomeVisitor();
      signUp({ name: "Trần Văn Đăng", company: unique("Hải Đăng"), vat }).as("registered");

      cy.signInAs("sales");
      cy.openRecord(customer);
      cy.get("button[name=action_invite_to_portal]").click();
      cy.get(".modal").contains(".o_data_row", email).find("button[name=action_grant_access]").click();
      cy.get(".modal").contains(".o_data_row", email).find("button[name=action_revoke_access]").should("be.visible");
      call("res.users", "search_read", [[["login", "=", email]]], { fields: ["share"] }).then((users) => {
        expect(users, "portal user").to.have.length(1);
        expect(users[0].share).to.be.true;
      });
      cy.get(".modal .btn-close").click();

      call("medilab.customer", "search", [[["duplicate_of_id", "=", customerId]]]).then((duplicates) => {
        expect(duplicates, "flagged duplicate").to.have.length(1);
        cy.openRecord({ model: "medilab.customer", id: duplicates[0] });
        cy.get("button[name=action_merge_duplicate]").click();
        cy.get(".modal-footer .btn-primary").click();
        cy.location("pathname").should("contain", `/${customerId}`);
        call("medilab.customer", "search", [[["id", "=", duplicates[0]]]]).should("have.length", 0);
      });
      // The registered person now belongs to the customer that was kept.
      cy.get("@registered").then((login) =>
        call("res.users", "search_read", [[["login", "=", login]]], { fields: ["partner_id"] }).then(([user]) =>
          cy.readRecord(customer, ["child_ids"]).its("child_ids").should("include", user.partner_id[0]),
        ),
      );
    });
  });

  it("TC-SF09-A4 lets the customer rate a completed order", () => {
    const comment = unique("Fast results and a clear report.");
    orderIn("completed").then((order) => {
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}`);
      cy.get("main #rating-4").check();
      cy.get("main textarea[name=comment]").type(comment);
      cy.get(`main form[action='/orders/${order.id}/feedback'] button[type=submit]`).click();
      cy.contains("main", "4/5");
      cy.contains("main", comment);
      cy.get(`main form[action='/orders/${order.id}/feedback']`).should("not.exist");

      cy.signInAs("sales");
      cy.openRecord(order);
      openTab("feedback");
      cy.get(".o_field_widget[name=feedback_rating] input").should("have.value", "4");
      cy.get(".o_field_widget[name=feedback_comment] textarea").should("have.value", comment);
      // Management finds the newest feedback first.
      cy.signInAs("head_of_sales");
      cy.visit("/odoo/order-feedback");
      cy.get(".o_data_row").first().should("contain", order.name);
    });
  });

  it("TC-SF09-E1 refuses rating an order that is not completed, or rating it twice", () => {
    orderIn("confirmed").then((order) => {
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}`);
      cy.get("main h1").should("contain", order.name);
      cy.get(`main form[action='/orders/${order.id}/feedback']`).should("not.exist");
      callRefused("sale.order", "action_give_feedback", [[order.id], 5]).should("contain", "Feedback can be given once the order is completed.");
      cy.readRecord(order, ["feedback_rating"]).its("feedback_rating").should("eq", 0);
    });

    orderIn("completed").then((order) => {
      rateOrder(order, 5, "Very good.");
      cy.signInAs("customer");
      cy.visit(`/orders/${order.id}`);
      cy.contains("main", "5/5");
      cy.get(`main form[action='/orders/${order.id}/feedback']`).should("not.exist");
      callRefused("sale.order", "action_give_feedback", [[order.id], 1, "Changed my mind."]).should("contain", "This order already has feedback.");
      cy.readRecord(order, ["feedback_rating", "feedback_comment"]).should("deep.include", {
        feedback_rating: 5,
        feedback_comment: "Very good.",
      });
    });
  });

  it("TC-SF09-E2 never shows the customer's support requests or feedback to another customer", () => {
    const comment = unique("Only for our laboratory.");
    openRequest(unique("Private question")).then((request) => {
      orderIn("completed").then((order) => {
        rateOrder(order, 3, comment);
        cy.signInAs("individual");
        cy.visit("/support");
        cy.get("main").should("not.contain", request.subject);
        cy.request({ url: `/support/${request.id}`, failOnStatusCode: false })
          .its("status")
          .should("eq", 404);
        cy.request({ url: `/orders/${order.id}`, failOnStatusCode: false })
          .its("status")
          .should("eq", 404);
        callAs(OTHER_CUSTOMER, "medilab.support.request", "portal_requests", []).then((ids) => expect(ids).not.to.include(request.id));
        callRefused("rating.rating", "search_read", [[["res_id", "=", order.id]]], { fields: ["feedback"] });
      });
    });
  });
});

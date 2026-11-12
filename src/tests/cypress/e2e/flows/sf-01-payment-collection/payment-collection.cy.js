import { save } from "../../../support/form";
import { callAs, portalPostAs, refAs } from "../../../support/odoo";
import {
  ACCOUNTANT,
  ADMINISTRATOR,
  CUSTOMER,
  SALES,
  finalInvoice,
  notifyPayos,
  onlinePayments,
  openPayosLink,
  paidOrder,
  readInvoice,
  startPayos,
  transfer,
  unreconciledDay,
  unrecordedTransfer,
} from "./setup";

const PAID = ["paid", "in_payment"];

// The order's payment status, as sales reads it.
const orderPaymentStatus = (orderId) => callAs(SALES, "sale.order", "read", [[orderId], ["payment_status"]]).then(([read]) => read.payment_status);

// The order an invoice bills.
const invoiceOrder = (invoice) => readInvoice(invoice, ["order_id"]).then((read) => read.order_id[0]);

// Clicks a button of the open form's header and waits for its dialog.
function openDialog(button) {
  cy.get(`.o_form_view .o_statusbar_buttons ${button}:visible`).should("have.length", 1).click();
  return cy.get(".modal:visible").last();
}

// The accountant adjusts the invoice by `difference` with its Adjust dialog. Yields the adjustment invoice.
function adjust(invoice, difference) {
  cy.openRecord(invoice);
  return refAs(ADMINISTRATOR, "sol_commerce.action_medilab_invoice_adjustment").then(({ id }) => {
    openDialog(`button[name="${id}"]`).within(() => {
      cy.get(".o_field_widget[name=difference] input").clear().type(String(difference));
      cy.get("button[name=action_adjust]").click();
    });
    cy.location("pathname").should("not.match", new RegExp(`/${invoice.id}$`));
    return cy
      .location("pathname")
      .then((path) => readInvoice({ id: Number(path.split("/").pop()) }, ["move_type", "invoice_kind", "state", "amount_total"]))
      .then((read) => {
        expect(read.invoice_kind).to.equal("adjustment");
        expect(read.state).to.equal("posted");
        return read;
      });
  });
}

// Reads until `done` holds, every two seconds for at most `tries` reads.
function waitFor(read, done, tries = 45) {
  return read().then((value) => {
    if (done(value)) {
      return value;
    }
    expect(tries, "reads left").to.be.greaterThan(1);
    cy.wait(2000);
    return waitFor(read, done, tries - 1);
  });
}

// The administrator runs the overdue reminders from their scheduled job, which starts within a minute, and waits
// until that run has done every item.
function runOverdueReminders() {
  refAs(ADMINISTRATOR, "sol_commerce.scheduled_job_overdue_reminders").then((job) => {
    cy.openRecord(job);
    cy.get(".o_statusbar_buttons button[name=action_run]:visible").click();
    cy.get(".o_notification").should("be.visible");
    waitFor(
      () => callAs(ADMINISTRATOR, job.model, "read", [[job.id], ["run_requested_by_id", "last_run_status", "pending_count"]]),
      ([read]) => !read.run_requested_by_id && read.last_run_status !== "running" && read.pending_count === 0,
    );
  });
}

// Today's overdue reminders of the invoice.
function reminders(invoice) {
  const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Ho_Chi_Minh" });
  return callAs(ADMINISTRATOR, "mail.message", "search_read", [[["notification_key", "=", `invoice:${invoice.id}:overdue:${today}`]]], {
    fields: ["id"],
  });
}

describe("SF-01 Invoicing and payment collection", () => {
  it("TC-SF01-M bills the rest of a paid order, which the customer pays online and receives a receipt for", () => {
    paidOrder().then((order) => {
      // The final invoice bills what is left after the 30% advance.
      const billed = Math.round(order.amount_total * 0.7);
      cy.signInAs("accountant");
      cy.openRecord(order);
      openDialog("button#create_invoice").within(() => {
        cy.get(".o_field_widget[name=advance_payment_method] input[data-value=delivered]").should("be.checked");
        cy.get("button[name=create_invoices]").click();
      });
      cy.location("pathname").should("match", /\/invoicing\/\d+$/);
      cy.location("pathname").then((path) => {
        const invoice = { model: "account.move", id: Number(path.split("/").pop()) };
        readInvoice(invoice, ["invoice_kind", "state", "amount_total"]).then((read) => {
          expect(read.invoice_kind).to.equal("final");
          expect(read.state).to.equal("draft");
          expect(read.amount_total).to.equal(billed);
        });
        cy.get(".o_statusbar_buttons button[name=action_post]:visible").click();
        cy.intercept("POST", "/web/dataset/call_button/account.move/action_send_invoice").as("email");
        cy.get(".o_statusbar_buttons button[name=action_send_invoice]:visible").click();
        cy.wait("@email");
        // The customer is sent the invoice PDF.
        callAs(ACCOUNTANT, "mail.message", "search_read", [[["notification_key", "=", `invoice:${invoice.id}:sent`]]], {
          fields: ["attachment_ids"],
        })
          .its("0.attachment_ids")
          .should("have.length", 1);

        cy.signInAs("customer");
        cy.visit(`/my/invoices/${invoice.id}`);
        cy.get("button[name=method][value=payos]").click();
        cy.get("#payos-pending").should("be.visible");
        openPayosLink(invoice).then((link) => notifyPayos(transfer(link)));

        readInvoice(invoice, ["amount_residual", "payment_state"]).then((read) => {
          expect(read.amount_residual).to.equal(0);
          expect(read.payment_state).to.be.oneOf(PAID);
        });
        orderPaymentStatus(order.id).should("eq", "paid");
        onlinePayments(invoice).then(([payment]) => {
          expect(payment.state, "confirmed").to.be.oneOf(["paid", "reconciled"]);
          cy.visit(`/my/invoices/${invoice.id}`);
          cy.get("#medilab_payment_amount").should("not.exist");
          cy.visit(`/my/invoices/${invoice.id}/receipt/${payment.id}`);
          cy.contains("body", new RegExp(billed.toLocaleString("en-US").replaceAll(",", "[.,]")));
        });
      });
    });
  });

  it("TC-SF01-A1 takes part of the invoice online, then the rest, leaving it partially paid in between", () => {
    finalInvoice().then((invoice) => {
      readInvoice(invoice, ["amount_residual"]).then(({ amount_residual: owed }) => {
        const part = 100000;
        cy.signInAs("customer");
        cy.visit(`/my/invoices/${invoice.id}`);
        cy.get("#medilab_payment_amount").clear().type(String(part));
        cy.get("button[name=method][value=payos]").click();
        cy.get("#payos-pending").should("be.visible");
        openPayosLink(invoice).then((link) => {
          expect(link.amount).to.equal(part);
          notifyPayos(transfer(link));
        });
        readInvoice(invoice, ["amount_residual", "payment_state"]).should((read) => {
          expect(read.amount_residual).to.equal(owed - part);
          expect(read.payment_state).to.equal("partial");
        });
        invoiceOrder(invoice).then((orderId) => orderPaymentStatus(orderId).should("eq", "partial"));

        cy.visit(`/my/invoices/${invoice.id}`);
        cy.get("#medilab_payment_amount")
          .invoke("val")
          .then(Number)
          .should("eq", owed - part);
        cy.get("button[name=method][value=payos]").click();
        cy.get("#payos-pending").should("be.visible");
        openPayosLink(invoice).then((link) => notifyPayos(transfer(link)));
        readInvoice(invoice, ["amount_residual", "payment_state"]).should((read) => {
          expect(read.amount_residual).to.equal(0);
          expect(read.payment_state).to.be.oneOf(PAID);
        });
        invoiceOrder(invoice).then((orderId) => orderPaymentStatus(orderId).should("eq", "paid"));
        onlinePayments(invoice).its("length").should("eq", 2);
      });
    });
  });

  it("TC-SF01-A3 rejects a pending payment with a reason, tells the salesperson and leaves the invoice as it was", () => {
    const reason = "The transfer did not reach the bank account.";
    finalInvoice().then((invoice) => {
      const page = `/my/invoices/${invoice.id}`;
      portalPostAs(CUSTOMER.login, page, `${page}/pay`, { method: "bank_transfer", amount: 50000 });
      callAs(ACCOUNTANT, "account.payment", "search", [
        [
          ["invoice_ids", "in", [invoice.id]],
          ["state", "=", "draft"],
        ],
      ]).then(([paymentId]) => {
        const payment = { model: "account.payment", id: paymentId };
        cy.signInAs("accountant");
        cy.openRecord(payment);
        cy.get(".o_field_widget[name=rejection_reason] textarea").type(reason);
        save();
        cy.get(".o_statusbar_buttons button[name=action_reject_payment]:visible").click();
        cy.get(".o_statusbar_buttons button[name=action_reject_payment]:visible").should("not.exist");
        cy.readRecord(payment, ["state", "reviewed_by_id"]).should((read) => {
          expect(read.state).to.equal("canceled");
          expect(read.reviewed_by_id[1]).to.be.a("string").and.not.be.empty;
        });
        readInvoice(invoice, ["payment_state"]).its("payment_state").should("eq", "not_paid");
        refAs(SALES, "sol_demo.demo_res_users_sales").then(({ id: salesId }) =>
          callAs(
            ACCOUNTANT,
            "mail.activity",
            "search_read",
            [
              [
                ["res_model", "=", "account.payment"],
                ["res_id", "=", paymentId],
              ],
            ],
            { fields: ["user_id", "note"] },
          ).then(([activity]) => {
            expect(activity.user_id[0], "the salesperson").to.equal(salesId);
            expect(activity.note).to.contain(reason);
          }),
        );
      });
    });
  });

  it("TC-SF01-A4 lowers and raises what is owed with adjustment invoices and leaves the original invoice unchanged", () => {
    finalInvoice().then((invoice) => {
      readInvoice(invoice, ["amount_total", "amount_owed"]).then((before) => {
        cy.signInAs("accountant");
        adjust(invoice, -50000).then((lowering) => {
          expect(lowering.move_type).to.equal("out_refund");
          readInvoice(invoice, ["amount_total", "amount_owed"]).should((read) => {
            expect(read.amount_total, "original invoice").to.equal(before.amount_total);
            expect(read.amount_owed).to.equal(before.amount_owed - lowering.amount_total);
          });
          adjust(invoice, 20000).then((raising) => {
            expect(raising.move_type).to.equal("out_invoice");
            readInvoice(invoice, ["amount_total", "amount_owed"]).should((read) => {
              expect(read.amount_total, "original invoice").to.equal(before.amount_total);
              expect(read.amount_owed).to.equal(before.amount_owed - lowering.amount_total + raising.amount_total);
            });
          });
        });
      });
    });
  });

  it("TC-SF01-A5 reminds the customer of an invoice unpaid after its due date, once each day", () => {
    const due = new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10);
    finalInvoice({ values: { invoice_date: due, invoice_date_due: due, invoice_payment_term_id: false } }).then((invoice) => {
      readInvoice(invoice, ["is_overdue"]).its("is_overdue").should("eq", true);
      callAs(ACCOUNTANT, "account.move", "search", [[["is_overdue", "=", true]]]).should("include", invoice.id);
      cy.signInAs("administrator");
      runOverdueReminders();
      reminders(invoice).should("have.length", 1);
      // A second run on the same day does not remind the customer again.
      runOverdueReminders();
      reminders(invoice).should("have.length", 1);
    });
  });

  it("TC-SF01-A6 flags a PayOS transfer with no payment, whose payment the accountant posts before locking the day", () => {
    finalInvoice().then((invoice) => {
      unreconciledDay().then((day) => {
        unrecordedTransfer(invoice, day).then((transactionId) => {
          cy.signInAs("accountant");
          cy.visit("/odoo/reconciliation-days/new");
          // The accountant's language writes dates month first.
          const [year, month, date] = day.split("-");
          cy.get(".o_field_widget[name=day] input").clear().type(`${month}/${date}/${year}{enter}`);
          save();
          cy.get(".o_field_widget[name=missing_payment_count]").should("have.text", "1");
          cy.get(".o_field_widget[name=transaction_ids] .o_data_row").should("have.length", 1);
          cy.get(".o_statusbar_buttons button[name=action_post_missing_payments]:visible").click();
          cy.get(".o_field_widget[name=missing_payment_count]").should("have.text", "0");
          cy.get(".o_statusbar_buttons button[name=action_lock]:visible").click();
          cy.get(".o_statusbar_buttons button[name=action_lock]").should("not.exist");
          callAs(ACCOUNTANT, "payment.transaction", "read", [[transactionId], ["payment_id"]])
            .its("0.payment_id")
            .should("be.ok");
          readInvoice(invoice, ["payment_state"]).its("payment_state").should("be.oneOf", PAID);
          callAs(ACCOUNTANT, "medilab.reconciliation.day", "search_read", [[["day", "=", day]]], { fields: ["status"] })
            .its("0.status")
            .should("eq", "locked");
        });
      });
    });
  });

  it("TC-SF01-E1 refuses a payment above the amount still owed", () => {
    finalInvoice().then((invoice) => {
      readInvoice(invoice, ["amount_residual"]).then(({ amount_residual: owed }) => {
        expect(owed, "amount still owed").to.be.greaterThan(0);
        cy.signInAs("accountant");
        cy.openRecord(invoice);
        cy.expectRefusal({
          action: () => {
            openDialog("button[name=action_register_payment]").within(() => {
              cy.get(".o_field_widget[name=amount] input")
                .clear()
                .type(String(owed + 1000));
              cy.get("button[name=action_create_payments]").click();
            });
          },
          message: "A payment cannot be more than the amount still owed.",
          read: () => readInvoice(invoice, ["amount_residual", "payment_state"]),
        });
      });
    });
  });

  it("TC-SF01-E2 refuses editing a posted invoice", () => {
    finalInvoice().then((invoice) => {
      readInvoice(invoice, ["state"]).its("state").should("eq", "posted");
      cy.signInAs("accountant");
      cy.openRecord(invoice);
      cy.expectRefusal({
        action: () => cy.get(".o_statusbar_buttons button[name=button_draft]:visible").click(),
        message: "A posted invoice cannot be edited. Correct it with an adjustment invoice.",
        read: () => readInvoice(invoice, ["state", "amount_total", "write_date"]),
      });
    });
  });

  it("TC-SF01-E3 refuses changing an online payment of a locked day", () => {
    refAs(ACCOUNTANT, "sol_demo.demo_account_move_payos_locked").then((invoice) =>
      onlinePayments(invoice).then(([payment]) => {
        expect(payment, "online payment of the locked day").to.exist;
        const record = { model: "account.payment", id: payment.id };
        cy.signInAs("accountant");
        cy.openRecord(record);
        cy.expectRefusal({
          action: () => cy.get(".o_statusbar_buttons button[name=action_draft]:visible").click(),
          message: "An online payment of a locked day cannot be changed.",
          read: () => cy.readRecord(record, ["state", "amount", "write_date"]),
        });
      }),
    );
  });

  it("TC-SF01-E4 records one payment for a repeated PayOS notification", () => {
    finalInvoice().then((invoice) => {
      startPayos(invoice).then((link) => {
        const data = transfer(link);
        notifyPayos(data);
        notifyPayos(data);
      });
      onlinePayments(invoice).its("length").should("eq", 1);
      readInvoice(invoice, ["amount_residual"]).its("amount_residual").should("eq", 0);
    });
  });
});

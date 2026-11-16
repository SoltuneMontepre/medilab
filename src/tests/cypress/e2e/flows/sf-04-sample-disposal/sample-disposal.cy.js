import { save, search } from "../../../support/form";
import { callRefused, refAs } from "../../../support/odoo";
import { SAMPLE_TYPES, TESTER, cancelledSample, disposedSample, remindRetention, reportedSample, retentionTasks } from "./setup";

const DISPOSE = ".o_statusbar_buttons button[name=action_dispose]";

// The tester disposes of the open sample and confirms that it cannot be undone.
function dispose() {
  cy.get(DISPOSE).should("be.visible").click();
  cy.get(".modal").should("contain", "cannot be undone");
  cy.get(".modal .modal-footer .btn-primary").click();
}

// The tester has disposed of the sample by the method, and its form no longer offers to dispose of it.
function expectDisposed(sample, method) {
  cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Disposed");
  cy.get(DISPOSE).should("not.exist");
  refAs(TESTER, "sol_demo.demo_person_tester").then((tester) =>
    cy.readRecord(sample, ["status", "disposal_note", "disposed_at", "disposed_by_id"]).should((read) => {
      expect(read.status).to.equal("disposed");
      expect(read.disposal_note).to.equal(method);
      expect(read.disposed_at, "disposed at").to.be.a("string");
      expect(read.disposed_by_id[0], "disposed by").to.equal(tester.id);
    }),
  );
}

describe("SF-04 Sample retention and disposal", () => {
  it("TC-SF04-M puts a kept sample whose retention has ended on the tester's to-do, where the tester records its disposal", () => {
    reportedSample(SAMPLE_TYPES.bottledWater, { retainedFor: -1 }).then((sample) => {
      remindRetention();
      retentionTasks(sample).should((tasks) => {
        expect(tasks, "retention tasks").to.have.length(1);
        expect(tasks[0].department_id[1]).to.equal("Chemistry");
        expect(tasks[0].status).to.equal("open");
      });

      cy.signInAs("tester");
      cy.visit("/odoo/awaiting-tasks");
      search(sample.code);
      cy.contains(".o_data_row", sample.code).find("button[name=action_claim]").click();
      cy.contains(".o_data_row", sample.code).should("not.exist");
      cy.visit("/odoo/my-tasks");
      search(sample.code);
      // A task of a document opens its document.
      cy.contains(".o_data_row", sample.code).click();
      cy.location("pathname").should("contain", `/medilab.sample/${sample.id}`);
      cy.get(".o_field_widget[name=code]").should("contain", sample.code);

      dispose();
      expectDisposed(sample, "Pour into the drain and recycle the bottles.");
      retentionTasks(sample).its("0.status").should("eq", "done");
    });
  });

  it("TC-SF04-A1 disposes of a sample that is not kept right after its report, by its sample type's method", () => {
    reportedSample(SAMPLE_TYPES.cabbage).then((sample) => {
      cy.signInAs("tester");
      cy.openRecord(sample);
      cy.get(".o_field_widget[name=retained_until]").should("have.text", "");

      dispose();
      expectDisposed(sample, "Dispose of as organic waste.");
      retentionTasks(sample).should("be.empty");
    });
  });

  it("TC-SF04-A2 disposes of a sample of a cancelled request by the method the tester enters on it", () => {
    cancelledSample().then((sample) => {
      cy.signInAs("tester");
      cy.openRecord(sample);
      cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Cancelled");
      cy.get(".o_field_widget[name=disposal_note] textarea").clear().type("Autoclave, then pour into the drain.");
      save();

      dispose();
      expectDisposed(sample, "Autoclave, then pour into the drain.");
    });
  });

  it("TC-SF04-E1 refuses to dispose of a sample with no method on it or its sample type", () => {
    reportedSample(SAMPLE_TYPES.surfaceWater).then((sample) => {
      cy.signInAs("tester");
      cy.openRecord(sample);
      cy.get(".o_field_widget[name=disposal_note] textarea").should("have.value", "");
      cy.expectRefusal({
        read: () => cy.readRecord(sample, ["status", "disposal_note", "disposed_at", "disposed_by_id", "write_date"]),
        action: dispose,
        message: `Sample ${sample.code} needs a disposal method, on the sample or on its sample type.`,
      });
    });
  });

  it("TC-SF04-E2 offers no way to dispose of a disposed sample again or change it back", () => {
    disposedSample().then((sample) => {
      cy.signInAs("tester");
      cy.openRecord(sample);
      cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Disposed");
      cy.get(DISPOSE).should("not.exist");
      cy.get(".o_field_widget[name=disposal_note] textarea").should("not.exist");
      cy.readRecord(sample, ["status", "disposal_note", "disposed_at", "disposed_by_id", "write_date"]).then((before) => {
        callRefused("medilab.sample", "action_dispose", [[sample.id]]).should("eq", "A disposed sample cannot be disposed of again.");
        callRefused("medilab.sample", "write", [[sample.id], { status: "retained" }]).should(
          "eq",
          `A disposed sample cannot be changed back: ${sample.code}`,
        );
        cy.readRecord(sample, ["status", "disposal_note", "disposed_at", "disposed_by_id", "write_date"]).should("deep.equal", before);
      });
    });
  });
});

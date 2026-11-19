import { callAs, refAs } from "../../../../support/odoo";
import { ADMIN } from "../../../flows/wf-06-report-release/setup";

describe("Scheduled jobs and cleanup (F-52)", () => {
  it("TC-F52-01 lists every scheduled job with its runs and runs one by hand", () => {
    refAs(ADMIN, "sol_demo.demo_scheduled_job_echo").then((job) => {
      cy.signInAs("administrator");
      cy.visit("/odoo/scheduled-jobs");
      cy.get(".o_list_renderer thead").should("contain", "Next");
      cy.openRecord(job);
      cy.get("button[name=action_run]").click();
      cy.readRecord(job, ["display_name"]).then(({ display_name }) =>
        cy.contains(".o_notification", `${display_name} runs within a minute.`).should("be.visible"),
      );
    });
  });

  it("TC-F52-03 keeps old audit entries in a checked archive file once the cleanup removes them", () => {
    refAs(ADMIN, "sol_demo.demo_archive_file_audit").then((archive) =>
      callAs(ADMIN, "medilab.archive.file", "read", [
        [archive.id],
        ["kind", "period_start", "period_end", "row_count", "checksum", "attachment_id"],
      ]).then(([file]) => {
        expect(file.kind).to.equal("audit_entry");
        expect(file.row_count).to.be.greaterThan(0);
        expect(file.checksum).to.match(/^[0-9a-f]{64}$/);
        callAs(ADMIN, "medilab.audit.entry", "search_count", [
          [
            ["create_date", ">=", `${file.period_start} 00:00:00`],
            ["create_date", "<=", `${file.period_end} 23:59:59`],
          ],
        ]).should("eq", 0);
        // The regulation the seeded old notification was about stays.
        refAs(ADMIN, "sol_demo.demo_regulation_qcvn_6_1").then(({ model, id }) =>
          callAs(ADMIN, model, "search_count", [[["id", "=", id]]]).should("eq", 1),
        );
        cy.signInAs("administrator");
        cy.request(`/web/content/${file.attachment_id[0]}?download=true`).its("status").should("eq", 200);
      }),
    );
  });
});

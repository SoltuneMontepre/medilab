import { randomId, refAs, signIn } from "../../../../support/odoo";
import { onPhone, signedInPhone } from "../../../../support/phone";

const STAFF = "demo.sample_delivery_staff";
const TESTER = "demo.tester";
// A photo as the phone sends it: PNG bytes in base64.
const PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

describe("Medilab Mobile sample photos on the web", () => {
  it("TC-F519-A1 shows a photo taken on the phone at collection on the sample on the web, and never to a tester", () => {
    refAs(STAFF, "sol_demo.demo_task_sample_collection_planned").then(({ id: taskId }) => {
      signedInPhone(STAFF).then((key) => {
        onPhone(key, "GET", `/tasks/${taskId}`).then(({ status, body: task }) => {
          expect(status).to.eq(200);
          expect(task.planned_start).to.be.a("string");
          expect(task.note).to.contain("Lê Văn Sỹ");
          expect(task.samples).to.have.length(1);
          const [{ id: sampleId }] = task.samples;
          const name = `collected-${Date.now()}.png`;
          const photo = { name, mimetype: "image/png", data: PNG };
          const sent = { "Idempotency-Key": randomId() };

          onPhone(key, "POST", `/samples/${sampleId}/photos`, photo, sent).then(({ status: first, body: attached }) => {
            expect(first).to.eq(200);
            // A photo sent again after a lost answer is attached once.
            onPhone(key, "POST", `/samples/${sampleId}/photos`, photo, sent).its("body.id").should("eq", attached.id);

            signIn(STAFF);
            cy.visit(`/odoo/medilab.sample/${sampleId}`);
            cy.get(".o_notebook .nav-link[name=photos]").click();
            cy.get('.o_field_widget[name="photo_ids"]').should("contain", name);

            signedInPhone(TESTER).then((testerKey) => {
              onPhone(testerKey, "GET", `/attachments/${attached.id}`).its("status").should("eq", 404);
              onPhone(testerKey, "GET", `/samples/${sampleId}/photos`).its("body.photos").should("deep.eq", []);
            });
            signIn(TESTER);
            cy.visit(`/odoo/medilab.sample/${sampleId}`);
            cy.get(".o_form_view").should("be.visible");
            cy.get(".o_notebook .nav-link[name=photos]").should("not.exist");
          });
        });
      });
    });
  });
});

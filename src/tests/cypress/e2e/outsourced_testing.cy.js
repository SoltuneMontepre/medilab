const PASSWORD = "demo";
const REASON = "Máy AAS đang sửa, cần kết quả trước hạn.";

function signIn(login) {
  cy.visit("/web/login");
  cy.get("input[name=login]").type(login);
  cy.get("input[name=password]").type(`${PASSWORD}{enter}`);
  cy.location("pathname").should("match", /^\/odoo/);
}

function call(model, method, args, kwargs = {}) {
  return cy
    .request("POST", `/web/dataset/call_kw/${model}/${method}`, {
      jsonrpc: "2.0",
      method: "call",
      params: { model, method, args, kwargs },
    })
    .then(({ body }) => {
      expect(body.error, JSON.stringify(body.error)).to.be.undefined;
      return body.result;
    });
}

// The lab code of the sample of a demo sample test.
function sampleCode(xmlId) {
  return call("ir.model.data", "check_object_reference", ["sol_demo", xmlId])
    .then(([, id]) => call("medilab.sample.test", "read", [[id], ["sample_id"]]))
    .then(([test]) => test.sample_id[1]);
}

// Opens a sample test from its testing task, as the head of department does.
function openTest(code) {
  cy.visit("/odoo/all-tasks");
  cy.contains(".o_data_row", code).click();
  cy.get(".o_form_view .o_form_statusbar").should("be.visible");
}

const outsourceButton = ".o_form_statusbar .o_statusbar_buttons .btn-success";

describe("Outsourced testing", () => {
  beforeEach(() => signIn("demo.head_of_department"));

  it("TC-F39-01 lets the head of department outsource a test straight away with a reason", () => {
    sampleCode("demo_sample_test_lead_emergency").then((code) => {
      openTest(code);
      cy.get(outsourceButton).click();
      cy.get(".modal [name=reason] textarea").type(REASON);
      cy.get(".modal button[name=action_outsource]").click();

      cy.get(".modal").should("not.exist");
      cy.contains(".o_form_view .o_data_row", code).should("be.visible");
    });
  });

  it("TC-F39-03 refuses outsourcing straight away without a reason, or a test in testing", () => {
    sampleCode("demo_sample_test_lead_today").then((code) => {
      openTest(code);
      cy.get(outsourceButton).click();
      cy.get(".modal button[name=action_outsource]").click();

      cy.get(".modal [name=reason].o_field_invalid").should("be.visible");
      cy.get(".modal").should("exist");
    });
    sampleCode("demo_sample_test_lead_running").then((code) => {
      openTest(code);
      cy.get(outsourceButton).should("not.exist");
    });
  });
});

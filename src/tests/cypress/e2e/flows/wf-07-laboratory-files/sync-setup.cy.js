import { call } from "../../../support/odoo";

const RELEASES = "https://github.com/SoltuneMontepre/medilab/releases/latest";
const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36";

// A testing task the tester reads.
function testingTask() {
  return call("medilab.task", "search_read", [[["document_model", "=", "medilab.sample.test"]], ["id"]], { limit: 1 }).then(
    ([task]) => {
      expect(task, "a testing task").to.exist;
      return task.id;
    },
  );
}

function redirect(url, headers = {}) {
  return cy.request({ url, headers, followRedirect: false }).then(({ status, headers: answer }) => {
    expect(status, url).to.eq(303);
    return answer.location;
  });
}

describe("Setting Medilab Sync up from a testing task", () => {
  beforeEach(() => {
    cy.signInAs("tester");
  });

  it("offers to download Medilab Sync and to open it on this MediLab", () => {
    testingTask().then((id) => cy.visit(`/odoo/all-tasks/${id}`));
    cy.contains(".o-form-buttonbox button", "Download Medilab Sync").should("be.visible");
    cy.contains(".o-form-buttonbox button", "Open in Medilab Sync").should("be.visible");

    redirect("/medilab/sync/download", { "User-Agent": WINDOWS }).should(
      "eq",
      `${RELEASES}/download/medilab-sync-windows-x64-setup.exe`,
    );
    redirect("/medilab/sync/connect").then((link) => {
      const url = new URL(link);
      expect(`${url.protocol}//${url.host}`).to.eq("medilab-sync://connect");
      expect(url.searchParams.get("server")).to.match(/^https?:\/\//);
    });
  });
});

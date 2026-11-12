import { callAs, randomId } from "../../../support/odoo";
import { ADMINISTRATOR, HEAD, OTHER_TESTER, PARAMETERS, TESTER, assign, receivedSample } from "../wf-03-testing-scheduling/setup";
import { api, ok, signInDevice } from "./device";

export { ADMINISTRATOR, HEAD, OTHER_TESTER, TESTER };
export const MICROBIOLOGY_TESTER = "demo.microbiology_tester";
export const SALES = "demo.sales";

// Names of computers and folders carry the run, so a test never meets what an earlier run of it left.
export function runTag() {
  return Date.now().toString(36);
}

// A person given by their login: their id and the name Odoo shows.
export function person(login) {
  return callAs(ADMINISTRATOR, "res.users", "search_read", [[["login", "=", login]]], { fields: ["name"] }).then(([user]) => user);
}

// A folder of the device's person, created as Medilab Sync creates one: owned by them, of no sample, upload only.
export function ownFolder(device, name) {
  return api(device, "POST", "/folders", { body: { name }, headers: { "Idempotency-Key": randomId() } }).then(
    (response) => ok(response, `create folder ${name}`).folder,
  );
}

// A sample received in good condition and assigned to the tester, whose department has a head of department; it has no
// folders yet.
export function sampleWithoutFolders() {
  return receivedSample([PARAMETERS.lead]).then((sample) => {
    assign(sample);
    return cy.then(() => sample);
  });
}

// The folders of a sample as the administrator reads them, by category.
export function foldersOfSample(sample) {
  return callAs(ADMINISTRATOR, "medilab.laboratory.folder", "search_read", [[["sample_id", "=", sample.id]]], {
    fields: ["name", "category", "owner_id", "sync_mode"],
  });
}

// The members of folders as the administrator reads them.
export function membersOf(folderIds) {
  return callAs(ADMINISTRATOR, "medilab.laboratory.folder.member", "search_read", [[["folder_id", "in", folderIds]]], {
    fields: ["folder_id", "user_id", "role"],
  });
}

// The state the stack declares for the editing service: down unless CYPRESS_editingService says up. Any other value is a
// mistake of the run, not a state.
export function editingService() {
  return cy.env(["editingService"]).then(({ editingService: declared = "down" }) => {
    expect(["down", "up"], `CYPRESS_editingService is "${declared}"`).to.include(declared);
    return declared;
  });
}

// The editor page of a file that is edited online must answer as the declared state says. A stack in another state fails the
// test, naming the way to bring them together.
export function expectEditorPage(file) {
  return editingService().then((declared) => {
    const mismatch = `The editing service is declared ${declared}: ${declared === "down" ? "run `task onlyoffice:down`" : "start it"}, or declare it with CYPRESS_editingService`;
    cy.request({ url: `/medilab/laboratory-files/${file.id}/edit`, failOnStatusCode: false }).then((page) => {
      if (declared === "down") {
        expect(page.status, mismatch).to.eq(503);
        expect(page.body).to.contain("Online editing is unavailable");
        return;
      }
      expect(page.status, mismatch).to.eq(200);
      const main = new DOMParser().parseFromString(page.body, "text/html").getElementById("laboratory-editor");
      expect(main.dataset.editorConfig, "editor configuration").to.not.be.empty;
      cy.request({ url: main.dataset.scriptUrl, failOnStatusCode: false }).its("status", { log: false }).should("eq", 200);
    });
  });
}

export function confirmDialog() {
  cy.get(".modal-footer .btn-primary").click();
}

// A person's device adds a person to a folder, as the owner's Medilab Sync does.
export function addMember(device, folder, user) {
  return api(device, "POST", `/folders/${folder.id}/members`, { body: { user_id: user.id } }).then(
    (response) => ok(response, `add ${user.name}`).member,
  );
}

// The devices of the people, signed in as computers named after the test.
export function devices(tag, ...logins) {
  const signedIn = [];
  logins.forEach((login, index) => signInDevice(login, `PC-${tag}-${index}`).then((device) => signedIn.push(device)));
  return cy.then(() => signedIn);
}

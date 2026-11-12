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

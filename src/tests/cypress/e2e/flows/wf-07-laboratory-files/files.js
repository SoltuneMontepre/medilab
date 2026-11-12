import { randomId } from "../../../support/odoo";
import { api, ok, sha256Of } from "./device";

const FIXTURES = "cypress/fixtures/laboratory";
const TERMINAL = ["completed", "conflict", "unchanged", "failed", "refused"];
const POLLS = 40;

function hexDigest(bytes) {
  return crypto.subtle
    .digest("SHA-256", bytes)
    .then((digest) => Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""));
}

// A fixture file as its bytes, size and SHA-256, read without any change to the bytes.
export function fixture(name) {
  return cy.readFile(`${FIXTURES}/${name}`, null).then((buffer) => {
    const bytes = new Uint8Array(buffer);
    return hexDigest(bytes).then((sha256) => ({ name, bytes, size: bytes.length, sha256 }));
  });
}

// An upload as Medilab Sync makes it: prepare, put the bytes into the bucket through the presigned address, finalize,
// then read the upload until the server has verified and stored it. Yields { upload } with the upload in its final
// state, or { refused } with the response of the prepare or the finalize that was refused.
export function upload(device, folder, path, fixtureName, { baseVersionId } = {}) {
  return fixture(fixtureName).then((content) =>
    api(device, "POST", `/folders/${folder.id}/uploads`, {
      body: { path, size: content.size, sha256: content.sha256, base_version_id: baseVersionId },
      headers: { "Idempotency-Key": randomId() },
    }).then((prepared) => {
      if (prepared.status !== 200) return { refused: prepared };
      const { id } = prepared.body.upload;
      return api(device, "POST", `/folders/${folder.id}/uploads/${id}/parts`, { body: { part_numbers: [1] } }).then((parts) =>
        // A Blob is the one request body Cypress sends byte for byte.
        cy
          .request({ method: "PUT", url: ok(parts, "part addresses").parts[0].url, body: new Blob([content.bytes]), failOnStatusCode: false })
          .then((put) => {
            expect(put.status, "part put").to.eq(200);
            return api(device, "POST", `/folders/${folder.id}/uploads/${id}/finalize`).then((finalized) =>
              finalized.status === 202 ? settled(device, folder, id).then((done) => ({ upload: done })) : { refused: finalized },
            );
          }),
      );
    }),
  );
}

// Reads an upload until it is in a final state; the verification takes the server a moment.
function settled(device, folder, uploadId, left = POLLS) {
  return api(device, "GET", `/folders/${folder.id}/uploads/${uploadId}`).then((response) => {
    const found = ok(response, "read upload").upload;
    if (TERMINAL.includes(found.status)) return found;
    expect(left, `upload ${uploadId} still ${found.status}`).to.be.greaterThan(0);
    cy.wait(250);
    return settled(device, folder, uploadId, left - 1);
  });
}

// The bytes of a version as the bucket gives them to a device: their size and SHA-256.
export function downloaded(device, folder, file, versionId) {
  return api(device, "POST", `/folders/${folder.id}/files/${file.id}/versions/${versionId}/download`).then((response) =>
    cy.request({ url: ok(response, "download address").url, encoding: "binary" }).then(({ status, body }) => {
      expect(status, "download").to.eq(200);
      return sha256Of(body).then((sha256) => ({ size: body.length, sha256 }));
    }),
  );
}

// The files of a folder as a device lists them.
export function filesOf(device, folder) {
  return api(device, "GET", `/folders/${folder.id}/files`).then((response) => ok(response, "list files").files);
}

// The file of a path in a folder.
export function fileAt(device, folder, path) {
  return filesOf(device, folder).then((files) => files.find((file) => file.path === path));
}

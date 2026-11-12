import { randomId, removeServiceWorkers } from "../../../support/odoo";

export const API = "/medilab/api/v1";

// The computers the running test signed in, which signOutDevices() signs out.
const signedIn = [];

// A computer of a person signed in as Medilab Sync signs it in, as a new installation. Yields what the application
// keeps: its installation id, its name and the device key, which Odoo shows only here.
export function signInDevice(login, name, platform = "linux") {
  const device = { login, name, platform, clientUid: randomId() };
  return cy
    .env(["demoPassword"])
    .then(({ demoPassword }) =>
      cy.request({
        method: "POST",
        url: `${API}/sign-in`,
        body: { login, password: demoPassword, client_uid: device.clientUid, name, platform },
        failOnStatusCode: false,
      }),
    )
    .then(({ status, body }) => {
      expect(status, `${login} signs in ${name}`).to.eq(200);
      const signed = { ...device, key: body.key, id: body.device.id };
      signedIn.push(signed);
      return signed;
    });
}

// Signing in an installation that is already known, which gets a new key, or a revoked one, which is refused.
export function signInAgain(device) {
  return cy.env(["demoPassword"]).then(({ demoPassword }) =>
    cy.request({
      method: "POST",
      url: `${API}/sign-in`,
      body: { login: device.login, password: demoPassword, client_uid: device.clientUid, name: device.name, platform: device.platform },
      failOnStatusCode: false,
    }),
  );
}

// A call of the laboratory files API as a device makes it, which carries no browser session: Odoo refuses a device key that
// comes with a session of another person as an invalid key, which a revoked key is answered with too. The session cookie
// goes just before the call, since a page of the back office that is still open can start a new one at any moment.
export function api(device, method, path, { body, qs, headers } = {}) {
  endBackOfficeSession();
  return cy.request({
    method,
    url: `${API}${path}`,
    qs,
    body,
    headers: { Authorization: `Bearer ${device.key}`, ...headers },
    failOnStatusCode: false,
  });
}

// Ends the back-office session of the browser, after the service worker of the back office, whose update check would open
// a new one. The next test signs in again through the cached session of cy.signInAs.
export function leaveBackOffice() {
  removeServiceWorkers();
  return endBackOfficeSession();
}

// A back-office page still open when its session ends is refused by Odoo with a session expiry, which is not a failure of
// the test that ended the session.
function endBackOfficeSession() {
  cy.on("uncaught:exception", (error) => !/Session Expired/.test(error.message));
  return cy.clearCookie("session_id");
}

// Signs out the computers the test signed in, so that none stays signed in. A revoked computer is refused, as it should be.
export function signOutDevices() {
  return cy.then(() => {
    signedIn.splice(0).forEach((device) => api(device, "POST", "/sign-out"));
  });
}

// The answer of a call that must succeed.
export function ok(response, what) {
  expect(response.status, `${what}: ${JSON.stringify(response.body)}`).to.be.within(200, 204);
  return response.body;
}

// The answer of a call that must be refused with the API's code and HTTP status.
export function refused(response, status, code, what) {
  expect(response.status, `${what}: ${JSON.stringify(response.body)}`).to.eq(status);
  expect(response.body.error.code, what).to.eq(code);
  return response.body.error;
}

// The SHA-256 of bytes read with cy.request({ encoding: "binary" }), as the hex text Odoo stores for a version.
export function sha256Of(binary) {
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return crypto.subtle
    .digest("SHA-256", bytes)
    .then((digest) => Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""));
}

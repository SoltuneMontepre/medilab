import { randomId, removeServiceWorkers } from "../../../support/odoo";

export const API = "/medilab/api/v1";

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
      return { ...device, key: body.key, id: body.device.id };
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

// A call of the laboratory files API as a device makes it. Odoo refuses a device key that comes with a browser session of
// another person, as an invalid key, which a revoked key is answered with too. The call therefore fails when the browser
// holds a back-office session instead of giving an answer that could be mistaken for a refusal; leaveBackOffice() ends it.
export function api(device, method, path, { body, qs, headers } = {}) {
  return cy.getCookie("session_id").then((cookie) => {
    expect(cookie, "a device call carries no back-office session; call leaveBackOffice() first").to.be.null;
    return cy.request({
      method,
      url: `${API}${path}`,
      qs,
      body,
      headers: { Authorization: `Bearer ${device.key}`, ...headers },
      failOnStatusCode: false,
    });
  });
}

// Ends the back-office session of the browser, so that device calls can follow the last screen of a test. The service
// worker of the back office goes first, since its update check would open a new session. The next test signs in again
// through the cached session of cy.signInAs.
export function leaveBackOffice() {
  removeServiceWorkers();
  return cy.clearCookie("session_id");
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

import { randomId } from "./odoo";

const API = "/medilab/api/v1";

// A phone of the person signed in as Medilab Mobile signs it in, as a new installation. Yields its device key.
export function signedInPhone(login) {
  return cy
    .env(["demoPassword"])
    .then(({ demoPassword }) =>
      cy.request("POST", `${API}/sign-in`, {
        login,
        password: demoPassword,
        client_uid: randomId(),
        name: `Pixel ${Date.now()}`,
        platform: "android",
      }),
    )
    .its("body.key");
}

// A call of Medilab Mobile with the phone's key; a refusal is answered, not failed.
export function onPhone(key, method, path, body, headers = {}) {
  return cy.request({
    method,
    url: `${API}${path}`,
    headers: { Authorization: `Bearer ${key}`, ...headers },
    body,
    failOnStatusCode: false,
  });
}

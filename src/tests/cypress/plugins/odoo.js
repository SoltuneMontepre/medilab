// Odoo sessions of the logins tests act as, kept for the whole run, so building a test's records
// never changes the browser's session or reloads the back office.

const { settingsTasks } = require("./settings");

function sessionCookie(response, current) {
  const cookie = response.headers.getSetCookie().find((value) => value.startsWith("session_id="));
  return cookie ? cookie.split(";")[0] : current;
}

function csrfToken(html, page) {
  const token = html.match(/csrf_token: "([^"]+)"/) || html.match(/name="csrf_token" value="([^"]+)"/);
  if (!token) {
    throw new Error(`No CSRF token on ${page}.`);
  }
  return token[1];
}

function odooTasks(baseUrl, password) {
  const sessions = new Map();

  async function request(cookie, path, init = {}) {
    const response = await fetch(new URL(path, baseUrl), {
      ...init,
      headers: { ...init.headers, ...(cookie && { Cookie: cookie }) },
      redirect: "manual",
    });
    return { response, cookie: sessionCookie(response, cookie) };
  }

  async function signIn(login) {
    const page = await request(null, "/web/login");
    const body = new URLSearchParams({ login, password, csrf_token: csrfToken(await page.response.text(), "/web/login") });
    const signedIn = await request(page.cookie, "/web/login", { method: "POST", body });
    if (signedIn.response.status !== 303 && signedIn.response.status !== 302) {
      throw new Error(`Signing in as ${login} failed.`);
    }
    return signedIn.cookie;
  }

  function session(login) {
    if (!sessions.has(login)) {
      const signingIn = signIn(login);
      signingIn.catch(() => sessions.delete(login));
      sessions.set(login, signingIn);
    }
    return sessions.get(login);
  }

  // A request in the login's session, keeping the cookie Odoo may rotate on the way.
  async function requestAs(login, path, init) {
    const { response, cookie } = await request(await session(login), path, init);
    sessions.set(login, Promise.resolve(cookie));
    return response;
  }

  async function call({ login, model, method, args = [], kwargs = {} }, retried = false) {
    const response = await requestAs(login, `/web/dataset/call_kw/${model}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { model, method, args, kwargs } }),
    });
    const reply = await response.json();
    if (reply.error) {
      if (reply.error.data?.name === "odoo.http.SessionExpiredException" && !retried) {
        sessions.delete(login);
        return call({ login, model, method, args, kwargs }, true);
      }
      throw new Error(`${login}: ${model}.${method} failed: ${reply.error.data?.message ?? reply.error.message}`);
    }
    // A task must not yield undefined.
    return reply.result ?? null;
  }

  // The portal answers a refused form with a redirect to the portal home or to a page with `error`.
  async function portalPost({ login, page, path, form = {} }) {
    const shown = await requestAs(login, page);
    const body = new URLSearchParams({ ...form, csrf_token: csrfToken(await shown.text(), page) });
    const response = await requestAs(login, path, { method: "POST", body });
    const location = new URL(response.headers.get("location") || path, baseUrl);
    if (response.status >= 400 || location.pathname === "/my" || location.searchParams.has("error")) {
      throw new Error(`${login}: posting ${path} was refused (${response.status} ${location.pathname}${location.search}).`);
    }
    return { status: response.status, location: location.pathname };
  }

  return { odooCall: call, odooPortalPost: portalPost, ...settingsTasks(call) };
}

module.exports = { odooTasks };

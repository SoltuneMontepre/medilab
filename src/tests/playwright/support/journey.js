// The journey's test object: its actors, its numbered steps and what each flow hands over to the next.

import fs from "node:fs";
import path from "node:path";
import { test as base, expect } from "@playwright/test";
import { signIn, watch } from "./odoo";

// MEDILAB_JOURNEY_VIDEO=0 runs the journey without recording each actor's screen.
const RECORD_VIDEO = process.env.MEDILAB_JOURNEY_VIDEO !== "0";
// MEDILAB_JOURNEY_STATE names another hand-over file, for a journey run beside the main one.
const STATE_FILE = process.env.MEDILAB_JOURNEY_STATE || path.join(__dirname, "..", ".output", "journey.json");

function readState() {
  return fs.existsSync(STATE_FILE) ? JSON.parse(fs.readFileSync(STATE_FILE, "utf8")) : {};
}

function writeState(state) {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, `${JSON.stringify(state, null, 2)}\n`);
}

// Starts a new journey: forgets what the last one handed over and gives every name it types a tag of its own, so the
// journey runs again on the same database.
export function startJourney() {
  const now = new Date();
  const pad = (number) => String(number).padStart(2, "0");
  const tag = `J${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  writeState({ tag });
  return tag;
}

// The tag of the journey under way; a flow run on its own starts one.
export function journeyTag() {
  return readState().tag ?? startJourney();
}

// Records what a flow leaves for the flows after it.
export function handOver(flow, values) {
  const state = readState();
  for (const [key, value] of Object.entries(values)) {
    state[key] = value;
    state.from = { ...state.from, [key]: flow };
  }
  writeState(state);
}

// What earlier flows left for this one. A flow whose starting records are missing is skipped with the names of what
// it did not receive, so the report shows where the chain broke.
export function received(...keys) {
  const state = readState();
  const missing = keys.filter((key) => state[key] === undefined || state[key] === null);
  base.skip(missing.length > 0, `Not handed over by an earlier flow: ${missing.join(", ")}`);
  return state;
}

export const test = base.extend({
  // Each actor works in a browser of their own, signed in through the login page.
  as: async ({ browser, baseURL }, use, testInfo) => {
    const actors = new Map();
    const open = async (login, password = process.env.MEDILAB_DEMO_PASSWORD || "demo") => {
      if (!actors.has(login)) {
        const context = await browser.newContext({
          baseURL,
          viewport: { width: 1440, height: 900 },
          timezoneId: "Asia/Ho_Chi_Minh",
          serviceWorkers: "block",
          acceptDownloads: true,
          recordVideo: RECORD_VIDEO ? { dir: testInfo.outputPath("videos", login) } : undefined,
        });
        const page = await context.newPage();
        watch(page);
        await signIn(page, login, password);
        actors.set(login, { context, page });
      }
      const { page } = actors.get(login);
      await page.bringToFront();
      return page;
    };
    // A visitor's browser, or one whose user signs in on the page itself.
    open.visitor = async (name) => {
      const context = await browser.newContext({
        baseURL,
        viewport: { width: 1440, height: 900 },
        timezoneId: "Asia/Ho_Chi_Minh",
        serviceWorkers: "block",
        acceptDownloads: true,
        recordVideo: RECORD_VIDEO ? { dir: testInfo.outputPath("videos", name) } : undefined,
      });
      const page = await context.newPage();
      watch(page);
      actors.set(name, { context, page });
      return page;
    };
    await use(open);
    for (const [login, { context, page }] of actors) {
      const video = page.video();
      await context.close();
      if (video) await testInfo.attach(`${login}.webm`, { path: await video.path(), contentType: "video/webm" });
    }
  },
});

let number = 0;
base.beforeEach(() => {
  number = 0;
});

// A business step of the flow, named with the words of its path in the business flows. The report keeps the screen
// as the step ends.
export async function step(page, name, run) {
  number += 1;
  const title = `${String(number).padStart(2, "0")} ${name}`;
  return base.step(title, async () => {
    try {
      return await run();
    } finally {
      const screenshot = await page.screenshot().catch(() => null);
      if (screenshot) await base.info().attach(title, { body: screenshot, contentType: "image/png" });
    }
  });
}

export { expect };

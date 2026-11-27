// What the Lab Head and the customer do with a test report's PDF: wait for it, review it, download it and read it.

import fs from "node:fs";
import zlib from "node:zlib";
import { expect } from "@playwright/test";
import { closeDialog, press, settled } from "./odoo";

function reviewButton(page) {
  return page.locator(".o_form_view:visible .o_statusbar_buttons button[name=action_open_candidate]");
}

// Waits on the open report for the PDF MediLab prepares on its own, opening the report again with `reopen` as a
// person does to see it. When none comes in time, the Lab Head has it prepared with Prepare PDF; a refused
// preparation fails with its reason.
export async function waitForPdf(page, reopen, { seconds = 90 } = {}) {
  const deadline = Date.now() + seconds * 1000;
  while (!(await reviewButton(page).isVisible()) && Date.now() < deadline) {
    await page.waitForTimeout(10000);
    await reopen();
  }
  if (await reviewButton(page).isVisible()) return;
  await press(page, "action_prepare_pdf", { refusals: true });
  const refusal = page.locator(".o_error_dialog .modal-body");
  if (await refusal.count()) {
    const reason = (await refusal.innerText()).trim();
    await closeDialog(page);
    expect(reason, "the report's PDF is prepared").toBeNull();
  }
  await expect(reviewButton(page)).toBeVisible();
}

// Opens the prepared PDF with Review PDF, which shows it in a tab of its own, and returns the PDF's file name.
export async function reviewPdf(page) {
  const [tab, pdf] = await Promise.all([
    page.waitForEvent("popup"),
    page.context().waitForEvent("response", (response) => response.url().includes("/web/content/")),
    reviewButton(page).click(),
  ]);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  await tab.close();
  await settled(page);
  return pdf.headers()["content-disposition"].match(/filename=([^;]+)/)[1];
}

// Clicks what downloads a file and returns the file's name and bytes.
export async function download(page, click) {
  const [file] = await Promise.all([page.waitForEvent("download"), click()]);
  return { name: file.suggestedFilename(), bytes: fs.readFileSync(await file.path()) };
}

// The text a PDF prints, read from its compressed page streams through its fonts' ToUnicode maps, with every space
// and line break left out: a PDF places words and lines by position, so its spaces are not reliable.
export function pdfText(bytes) {
  const pdf = bytes.toString("latin1");
  const objects = new Map([...pdf.matchAll(/(\d+) 0 obj([\s\S]*?)endobj/g)].map(([, id, body]) => [id, body]));
  const stream = (body = "") => {
    const start = body.indexOf("stream");
    if (start < 0) return "";
    const data = Buffer.from(body.slice(body.indexOf("\n", start) + 1, body.lastIndexOf("endstream")), "latin1");
    try {
      return /FlateDecode/.test(body.slice(0, start)) ? zlib.inflateSync(data).toString("latin1") : data.toString("latin1");
    } catch {
      return "";
    }
  };
  const characters = (hex) => Buffer.from(hex, "hex").swap16().toString("utf16le");
  const maps = new Map();
  for (const [id, body] of objects) {
    const toUnicode = body.match(/\/ToUnicode (\d+) 0 R/);
    if (!toUnicode) continue;
    const cmap = stream(objects.get(toUnicode[1]));
    const map = new Map();
    for (const [, block] of cmap.matchAll(/beginbfchar([\s\S]*?)endbfchar/g)) {
      for (const [, code, text] of block.matchAll(/<(\w+)>\s*<(\w+)>/g)) map.set(parseInt(code, 16), characters(text));
    }
    for (const [, block] of cmap.matchAll(/beginbfrange([\s\S]*?)endbfrange/g)) {
      for (const [, low, high, list, first] of block.matchAll(/<(\w+)>\s*<(\w+)>\s*(?:\[([^\]]*)\]|<(\w+)>)/g)) {
        const listed = list ? [...list.matchAll(/<(\w+)>/g)].map(([, text]) => characters(text)) : [];
        for (let code = parseInt(low, 16), shift = 0; code <= parseInt(high, 16); code++, shift++) {
          if (list) {
            map.set(code, listed[shift] ?? "");
          } else {
            // A range maps its codes to consecutive characters from the first one.
            const text = Buffer.from(first, "hex").swap16();
            text.writeUInt16LE(text.readUInt16LE(text.length - 2) + shift, text.length - 2);
            map.set(code, text.toString("utf16le"));
          }
        }
      }
    }
    maps.set(id, map);
  }
  let text = "";
  for (const body of objects.values()) {
    const content = stream(body);
    if (!/T[Jj]\b/.test(content)) continue;
    let font = new Map();
    for (const [operation] of content.matchAll(/\/\S+ [\d.]+ Tf|\[(?:[^\]\\]|\\.)*\]\s*TJ|<[\da-fA-F]*>\s*Tj/g)) {
      if (operation.endsWith("Tf")) {
        const resource = pdf.match(new RegExp(`/${operation.split(" ")[0].slice(1)} (\\d+) 0 R`));
        font = (resource && maps.get(resource[1])) ?? new Map();
      } else {
        for (const [, codes] of operation.matchAll(/<([\da-fA-F]*)>/g)) {
          for (let index = 0; index < codes.length; index += 4) text += font.get(parseInt(codes.slice(index, index + 4), 16)) ?? "";
        }
      }
    }
  }
  return text.replace(/\s+/g, "");
}

// A text as pdfText reads it, for finding it in a PDF; a decimal point may be printed as a comma.
export function printed(text) {
  return new RegExp(text.replace(/\s+/g, "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/(\d)\\\.(\d)/g, "$1[.,]$2"));
}

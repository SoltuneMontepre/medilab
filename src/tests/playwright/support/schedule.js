// What the head, the tester and the administrator do on the Machine Schedule: find a booking and read its slot.

import { field, listed, openMenu, search, settled, shownDay } from "./odoo";

export const MACHINE_SCHEDULE = ["sol_laboratory.menu_laboratory_root", "sol_laboratory.menu_laboratory_schedule", "sol_laboratory.menu_machine_booking"];

const LAB_OFFSET = "+07:00";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const pad = (number) => String(number).padStart(2, "0");

// The parts of an ISO moment of the laboratory's time, with the hour as a 12-hour clock writes it.
function clock(iso) {
  const [, year, month, day, hour, minute] = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/).map(Number);
  return { year, month, day, minute, hour: hour % 12 || 12, half: hour < 12 ? "AM" : "PM" };
}

// The laboratory time a screen writes like 11/27/2026 10:00 AM, as an ISO moment.
export function labMoment(text) {
  const [, month, day, year, hour, minute, half] = text.match(/(\d+)\/(\d+)\/(\d{4}),? (\d+):(\d+)(?::\d+)? (AM|PM)/);
  const hours = (Number(hour) % 12) + (half === "PM" ? 12 : 0);
  return `${year}-${pad(month)}-${pad(day)}T${pad(hours)}:${pad(minute)}:00${LAB_OFFSET}`;
}

// The ISO moment `minutes` later, in the laboratory's time.
export function later(iso, minutes) {
  const shifted = new Date(new Date(iso).getTime() + minutes * 60000 + 7 * 3600000);
  return `${shifted.toISOString().slice(0, 19)}${LAB_OFFSET}`;
}

// The ISO moment as a date-and-time field takes it in English: 11/27/2026 10:00:00 AM.
export function typedMoment(iso) {
  const { year, month, day, hour, minute, half } = clock(iso);
  return `${pad(month)}/${pad(day)}/${year} ${pad(hour)}:${pad(minute)}:00 ${half}`;
}

// The ISO moment as a field's tooltip writes it: 11/27/2026 10:00 AM.
export function shownMoment(iso) {
  const { year, month, day, hour, minute, half } = clock(iso);
  return `${pad(month)}/${pad(day)}/${year} ${pad(hour)}:${pad(minute)} ${half}`;
}

// The ISO moment as a list writes it, Nov 27, 10:00 AM, with the year for a day of another year.
export function listedMoment(iso) {
  const { year, month, day, hour, minute, half } = clock(iso);
  return new RegExp(`^${MONTHS[month - 1]} ${day},(?: ${year},?)? ${hour}:${pad(minute)} ${half}$`);
}

// Lists the bookings of a sample test that are not finished on the Machine Schedule, which opens as a calendar.
export async function findBookings(page, sampleTest) {
  await openMenu(page, ...MACHINE_SCHEDULE);
  await page.locator(".o_switch_view.o_list").click();
  await settled(page);
  await search(page, sampleTest, { field: "Sample Test" });
  return listed(page, sampleTest);
}

// The slot the open booking shows, as ISO moments.
export async function bookingSlot(page) {
  const moment = async (name) => labMoment(await shownDay(page, name).getAttribute("data-tooltip"));
  return { start: await moment("starts_at"), end: await moment("ends_at") };
}

// Types an ISO moment into a date-and-time field of the form.
export async function typeMoment(page, name, iso, within) {
  const widget = field(page, name, within);
  // A moment already set shows as a button until it is clicked.
  await widget.locator("input, button").first().click();
  const input = widget.locator("input").first();
  await input.fill(typedMoment(iso));
  await input.blur();
  await settled(page);
}

// The machine the open booking names, with its code, which only the machine's own form shows: the booking links to
// it. The machine's form stays open.
export async function bookingMachine(page) {
  const name = (await field(page, "machine_id").innerText()).trim();
  await field(page, "machine_id").locator("a").click();
  await settled(page);
  // The code is a text for who may only read the machine, and an input for who may edit it.
  const code = field(page, "code");
  await code.waitFor();
  const editable = code.locator("input");
  return { name, code: (await editable.count()) ? await editable.inputValue() : (await code.innerText()).trim() };
}

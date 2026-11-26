import { expect, handOver, received, step, test } from "../support/journey";
import { addLine, choose, discard, field, labDay, listed, openListed, openMenu, openNotices, openTab, press, save, search, settled, showList, status, toggleMessages, type, typeDate, written } from "../support/odoo";
import { MACHINE_SCHEDULE, bookingMachine, bookingSlot, findBookings, listedMoment, typedMoment } from "../support/schedule";

const MACHINES = ["sol_laboratory.menu_master_data_root", "sol_laboratory.menu_master_data_machines", "sol_laboratory.menu_machine"];

const REPAIRER = "PerkinElmer Vietnam";
const CALIBRATOR = "Quality Assurance and Testing Centre";
const ENGLISH_DAY = "mm/dd/yyyy";

test("SF-05 Machine calibration and unavailability", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "machineCodes", "testerName", "nitrateTaskName", "bookingMachine", "bookingMachineName", "bookingStart", "bookingEnd");
  const repaired = { code: journey.bookingMachine, name: journey.bookingMachineName };
  const otherCode = journey.machineCodes.find((code) => code !== repaired.code);
  const repairNote = `Lamp replaced ${journey.tag}`;
  const calibrationReference = `HC-${journey.tag}`;
  const booking = {};

  const admin = await as("demo.administrator");
  const services = () => field(admin, "service_ids").locator(".o_data_row");

  const openMachine = async () => {
    await openMenu(admin, ...MACHINES);
    await search(admin, repaired.code);
    await expect(listed(admin, repaired.name)).toHaveCount(1);
    await openListed(admin, repaired.name);
    await expect(field(admin, "code").locator("input")).toHaveValue(repaired.code);
  };

  // Chooses a status on the machine's status bar, which the form keeps until it is saved.
  const chooseStatus = async (value) => {
    await admin.locator(`.o_form_view:visible .o_statusbar_status button[data-value="${value}"]`).click();
    await settled(admin);
  };

  await step(admin, "The administrator finds the scheduled booking on the machine", async () => {
    const bookings = await findBookings(admin, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(repaired.name);
    await expect(bookings.locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(journey.bookingStart));
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
  });

  await step(admin, "The administrator records the downtime: the machine goes under repair", async () => {
    await openMachine();
    await expect(status(admin)).toHaveAttribute("data-value", "in_use");
    await openTab(admin, "methods");
    await expect(field(admin, "method_ids").locator(".o_data_row", { hasText: journey.methodCode })).toHaveCount(1);
    await chooseStatus("under_repair");
    await save(admin);
    await expect(status(admin)).toHaveAttribute("data-value", "under_repair");
  });

  await step(admin, "The not-started booking returns to the plan and moves to the other machine linked to the same method", async () => {
    const bookings = await findBookings(admin, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=status]")).toHaveText("Proposed");
    await expect(bookings.locator("td[name=machine_id]")).not.toHaveText(repaired.name);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(/\S/);
    await expect(bookings.locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(/\S/);
    await openListed(admin, journey.parameterName);
    await expect(status(admin)).toHaveAttribute("data-value", "proposed");
    await expect(field(admin, "method_id")).toHaveText(journey.methodCode);
    await expect(admin.locator(".o_form_view:visible .badge", { hasText: "Pinned" })).toHaveCount(0);
    booking.machine = await bookingMachine(admin);
    expect(booking.machine.code).toBe(otherCode);
  });

  await step(admin, "The schedule lists every booking of the machine under repair, finished ones included", async () => {
    await openMenu(admin, ...MACHINE_SCHEDULE);
    await showList(admin);
    await search(admin, repaired.name, { field: "Machine" });
    await expect(listed(admin, journey.nitrateTaskName)).toHaveCount(0);
    // A finished or cancelled booking keeps its slot on the machine, and the list works out its machine warning.
    await admin.locator(".o_searchview_facet", { hasText: "Not Finished" }).locator(".o_facet_remove").click();
    await settled(admin, { refusals: true });
    const failure = admin.locator(".o_error_dialog");
    await expect.soft(failure, "The schedule opens the bookings that keep a slot on a calibrated machine under repair").toHaveCount(0, { timeout: 1000 });
    if (await failure.count()) await failure.locator(".modal-footer button").first().click();
    await expect(admin.locator(".o_list_view:visible")).toBeVisible();
  });

  const tester = await as("demo.tester");

  await step(tester, "The tester is told that the booking returned to the plan", async () => {
    const notices = await openNotices(tester);
    await expect(notices.filter({ hasText: journey.nitrateTaskName }).first()).toBeVisible();
    const told = notices.filter({ hasText: journey.nitrateTaskName }).filter({ hasNotText: /assigned you|is approved|has been booked/ });
    await expect.soft(told, "A notice tells the tester that the machine's downtime returned the booking to the plan").not.toHaveCount(0, { timeout: 1000 });
    await toggleMessages(tester);
  });

  const head = await as("demo.head_of_department");

  await step(head, "The head approves the booking on the other machine", async () => {
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookings.locator("td[name=status]")).toHaveText("Proposed");
    await openListed(head, journey.parameterName);
    await expect(status(head)).toHaveAttribute("data-value", "proposed");
    await press(head, "action_approve");
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    await expect(field(head, "machine_id")).toHaveText(booking.machine.name);
    await expect(field(head, "person_id")).toHaveText(journey.testerName);
    await expect(head.locator(".o_form_view:visible .alert:visible")).toHaveCount(0);
    Object.assign(booking, await bookingSlot(head));
    expect(new Date(booking.start).getTime(), "The booking starts in the future").toBeGreaterThan(Date.now());
    await openTab(head, "room_bookings");
    await expect(field(head, "room_event_ids").locator(".o_data_row")).not.toHaveCount(0);
    handOver("SF-05", {
      bookingMachine: booking.machine.code,
      bookingMachineName: booking.machine.name,
      bookingStart: booking.start,
      bookingEnd: booking.end,
      bookingStatus: (await status(head).innerText()).trim(),
      bookingPinned: false,
    });
  });

  await step(tester, "The tester is notified of the booking's new slot", async () => {
    // The application lists a notice sent meanwhile once the page is loaded again.
    await tester.reload();
    await settled(tester);
    const notices = await openNotices(tester);
    await expect(notices.filter({ hasText: `${journey.nitrateTaskName} is approved: it starts at ${typedMoment(booking.start)}.` }).first()).toBeVisible();
    await expect(notices.filter({ hasText: `${booking.machine.name}: ${journey.nitrateTaskName}` }).first()).toContainText("has been booked");
    await toggleMessages(tester);
  });

  await step(admin, "The administrator records the repair of the machine", async () => {
    await openMachine();
    await expect(status(admin)).toHaveAttribute("data-value", "under_repair");
    await openTab(admin, "services");
    const repair = await addLine(admin, "service_ids");
    await choose(admin, "kind", "Repair", repair);
    await typeDate(admin, "service_date", labDay(), repair);
    await type(admin, "performed_by", REPAIRER, repair);
    await type(admin, "note", repairNote, repair);
    await save(admin);
    await expect(services().first()).toContainText(repairNote);
    await expect(services().first().locator("td[name=kind]")).toHaveText("Repair");
    await expect(status(admin)).toHaveAttribute("data-value", "under_repair");
  });

  await step(admin, "Returning the machine to use without a calibration after the repair is refused", async () => {
    await chooseStatus("in_use");
    await admin.locator(".o_form_button_save:visible").click();
    await settled(admin, { refusals: true });
    const refusal = admin.locator(".o_error_dialog");
    await expect(refusal).toContainText(`Record a calibration or maintenance of ${repaired.name} done after its repair on ${written(labDay(), ENGLISH_DAY)} before putting it back in use.`);
    await refusal.locator(".modal-footer button").first().click();
    await expect(refusal).toHaveCount(0);
    await discard(admin);
    await expect(status(admin)).toHaveAttribute("data-value", "under_repair");
  });

  await step(admin, "The administrator records a calibration after the repair and returns the machine to use", async () => {
    await openTab(admin, "services");
    const calibration = await addLine(admin, "service_ids");
    await choose(admin, "kind", "Calibration", calibration);
    await typeDate(admin, "service_date", labDay(), calibration);
    await typeDate(admin, "next_due_date", labDay({ years: 1 }), calibration);
    await type(admin, "performed_by", CALIBRATOR, calibration);
    await type(admin, "reference", calibrationReference, calibration);
    await save(admin);
    await expect(services().first()).toContainText(calibrationReference);
    await expect(services().first().locator("td[name=kind]")).toHaveText("Calibration");
    await expect(services().nth(1)).toContainText(repairNote);
    await chooseStatus("in_use");
    await save(admin);
    await expect(status(admin)).toHaveAttribute("data-value", "in_use");
    await openMenu(admin, ...MACHINES);
    await search(admin, repaired.code);
    await expect(listed(admin, repaired.name).locator("td[name=status]")).toHaveText("In use");
  });

  await step(admin, "The booking stays scheduled on the other machine", async () => {
    const bookings = await findBookings(admin, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookings.locator("td[name=person_id]")).toHaveText(journey.testerName);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(booking.start));
    await expect(bookings.locator("td[name=ends_at]")).toHaveText(listedMoment(booking.end));
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
  });

  await step(tester, "The tester finds the booking scheduled on the other machine, ready to start", async () => {
    const bookings = await findBookings(tester, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
    await openListed(tester, journey.parameterName);
    await expect(status(tester)).toHaveAttribute("data-value", "scheduled");
    expect(await bookingSlot(tester)).toEqual({ start: booking.start, end: booking.end });
    await expect(tester.locator(".o_form_view:visible .o_statusbar_buttons button[name=action_start]")).toBeVisible();
    handOver("SF-05", { bookingStatus: (await status(tester).innerText()).trim() });
  });
});

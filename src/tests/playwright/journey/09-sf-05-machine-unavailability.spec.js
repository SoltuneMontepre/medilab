import { expect, handOver, outside, received, step, test } from "../support/journey";
import { addLine, choose, field, labDay, listed, openListed, openMenu, openTab, press, save, search, settled, status, type, typeDate } from "../support/odoo";
import { bookingMachine, bookingSlot, findBookings, listedMoment } from "../support/schedule";

const MACHINES = ["sol_laboratory.menu_master_data_root", "sol_laboratory.menu_master_data_machines", "sol_laboratory.menu_machine"];

const REPAIRER = "PerkinElmer Vietnam";
const CALIBRATOR = "Quality Assurance and Testing Centre";

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

  await step(admin, "The administrator records the downtime: the machine of the scheduled booking goes under repair", async () => {
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
    await expect(bookings.locator("td[name=person_id]")).toHaveText(journey.testerName);
    await openListed(admin, journey.parameterName);
    await expect(status(admin)).toHaveAttribute("data-value", "proposed");
    await expect(field(admin, "method_id")).toHaveText(journey.methodCode);
    booking.machine = await bookingMachine(admin);
    expect(booking.machine.code).toBe(otherCode);
    // The booking left the slot WF-03 handed over; it has one again once the head approves it.
    handOver("SF-05", { bookingStatus: "Proposed", bookingMachine: null, bookingMachineName: null, bookingStart: null, bookingEnd: null });
  });

  const head = await as("demo.head_of_department");

  await step(head, "The tester and the head of department are notified that the booking moved", async () => {
    // With their default preferences the notices would go by e-mail, but the machine's downtime sends none.
    throw new Error("No notice tells the tester or the head of department that the machine's downtime returned the booking to the plan and moved it.");
  });

  await step(head, "The head approves the booking on the other machine", async () => {
    const bookings = await findBookings(head, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookings.locator("td[name=status]")).toHaveText("Proposed");
    await openListed(head, journey.parameterName);
    await press(head, "action_approve");
    await expect(status(head)).toHaveAttribute("data-value", "scheduled");
    await expect(field(head, "machine_id")).toHaveText(booking.machine.name);
    await expect(field(head, "person_id")).toHaveText(journey.testerName);
    Object.assign(booking, await bookingSlot(head));
    handOver("SF-05", {
      bookingMachine: booking.machine.code,
      bookingMachineName: booking.machine.name,
      bookingStart: booking.start,
      bookingEnd: booking.end,
      bookingStatus: (await status(head).innerText()).trim(),
    });
  });

  await outside("The tester is notified of the approved booking", "e-mail");

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

  await step(admin, "The administrator records a calibration after the repair and returns the machine to use", async () => {
    const calibration = await addLine(admin, "service_ids");
    await choose(admin, "kind", "Calibration", calibration);
    await typeDate(admin, "service_date", labDay(), calibration);
    await typeDate(admin, "next_due_date", labDay({ years: 1 }), calibration);
    await type(admin, "performed_by", CALIBRATOR, calibration);
    await type(admin, "reference", calibrationReference, calibration);
    await save(admin);
    await expect(services().first()).toContainText(calibrationReference);
    await expect(services().nth(1)).toContainText(repairNote);
    await chooseStatus("in_use");
    await save(admin);
    await expect(status(admin)).toHaveAttribute("data-value", "in_use");
  });

  await step(admin, "The booking stays scheduled on the other machine", async () => {
    const bookings = await findBookings(admin, journey.parameterName);
    await expect(bookings).toHaveCount(1);
    await expect(bookings.locator("td[name=machine_id]")).toHaveText(booking.machine.name);
    await expect(bookings.locator("td[name=starts_at]")).toHaveText(listedMoment(booking.start));
    await expect(bookings.locator("td[name=status]")).toHaveText("Scheduled");
  });
});

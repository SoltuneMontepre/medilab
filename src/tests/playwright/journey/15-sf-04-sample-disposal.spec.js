import { expect, handOver, received, step, test } from "../support/journey";
import { closeDialog, dated, field, labDay, listed, openListed, openMenu, openRow, openTab, press, search, settled, status } from "../support/odoo";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const SAMPLES = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample"];
const TEST_REPORTS = [LABORATORY, "sol_laboratory.menu_laboratory_results", "sol_laboratory.menu_test_report"];
const MY_TASKS = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_mine"];
const TASK_QUEUE = ["sol_laboratory.menu_tasks_root", "sol_laboratory.menu_task_queue"];

const ENGLISH_DAY = "mm/dd/yyyy";
const RETENTION_TASK = "Sample retention";

const iso = (date) => date.toISOString().slice(0, 10);
const shown = async (locator) => (await locator.innerText()).trim();

test("SF-04 Sample retention, return and disposal", async ({ as }) => {
  const journey = received("tag", "sampleLabCode", "sampleType", "replacementReportNumber", "sampleStatusAfterReport");
  const sample = {};
  const returnButton = (page) => page.locator(".o_form_view:visible .o_statusbar_buttons button[name=action_open_return]");

  const tester = await as("demo.tester");

  const openSample = async (page) => {
    await openMenu(page, ...SAMPLES);
    await openRow(page, journey.sampleLabCode);
    await expect(field(page, "code")).toHaveText(journey.sampleLabCode);
  };

  await step(tester, "The tester finds the reported sample, kept after testing until its retention date", async () => {
    await openMenu(tester, ...SAMPLES);
    await search(tester, journey.sampleLabCode);
    const row = listed(tester, journey.sampleLabCode);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=sample_type_id]")).toHaveText(journey.sampleType);
    await expect(row.locator("td[name=status]")).toHaveText(journey.sampleStatusAfterReport);
    await openListed(tester, journey.sampleLabCode);
    await expect(status(tester)).toHaveAttribute("data-value", "retained");
    await expect(field(tester, "disposed_at")).toHaveText("");
    await expect(field(tester, "disposed_by_id")).toHaveText("");
    const until = field(tester, "retained_until").locator("[data-tooltip]");
    await expect(until).toHaveAttribute("data-tooltip", /\d/);
    sample.retainedUntil = dated(await until.getAttribute("data-tooltip"), ENGLISH_DAY);
    expect(sample.retainedUntil > labDay(), "the retention period runs past today").toBe(true);
    handOver("SF-04", { retentionEnds: iso(sample.retainedUntil) });
  });

  await step(tester, "The tester reads the sample type's retention days and disposal method", async () => {
    await field(tester, "sample_type_id").locator("a").click();
    await settled(tester);
    await expect(field(tester, "name")).toHaveText(journey.sampleType);
    await expect(field(tester, "is_retained").locator("input")).toBeChecked();
    sample.retentionDays = Number(await shown(field(tester, "retention_days")));
    expect(sample.retentionDays).toBeGreaterThan(0);
    await expect(field(tester, "disposal_method")).toHaveText(/\S/);
    sample.method = await shown(field(tester, "disposal_method"));
    await tester.locator(".o_breadcrumb .breadcrumb-item a", { hasText: journey.sampleLabCode }).click();
    await settled(tester);
    await expect(field(tester, "code")).toHaveText(journey.sampleLabCode);
    handOver("SF-04", { retentionDays: sample.retentionDays, disposalMethod: sample.method });
  });

  await step(tester, "Disposing of the sample before its retention period ends is refused", async () => {
    await press(tester, "action_dispose");
    const confirmation = tester.locator(".modal:visible");
    await expect(confirmation.locator(".modal-body")).toHaveText("Dispose of this sample? This cannot be undone.");
    await confirmation.locator(".modal-footer .btn-primary").click();
    await settled(tester, { refusals: true });
    const refusal = tester.locator(".o_error_dialog");
    await expect(refusal.locator(".modal-body")).toHaveText(
      `Only a sample that is not kept, whose retention is over or whose test request was cancelled can be disposed of: ${journey.sampleLabCode}`,
    );
    await closeDialog(tester);
    await openSample(tester);
    await expect(status(tester)).toHaveAttribute("data-value", "retained");
    await expect(field(tester, "disposed_at")).toHaveText("");
  });

  await step(tester, "The tester's daily to-do has no retention task for the sample while its retention end is beyond the reminder days", async () => {
    for (const menu of [MY_TASKS, TASK_QUEUE]) {
      await openMenu(tester, ...menu);
      await search(tester, journey.sampleLabCode);
      await expect(listed(tester, journey.sampleLabCode).filter({ has: tester.locator("td[name=type_id]", { hasText: RETENTION_TASK }) })).toHaveCount(0);
    }
  });

  const staff = await as("demo.sample_delivery_staff");

  await step(staff, "SF-04-A3: The customer asks for the retained sample back; before its retention period ends the issued report offers no return", async () => {
    await openMenu(staff, ...TEST_REPORTS);
    await openRow(staff, journey.replacementReportNumber);
    await expect(status(staff)).toHaveAttribute("data-value", "issued");
    await openTab(staff, "samples");
    const row = field(staff, "sample_ids").locator(".o_data_row", { hasText: journey.sampleLabCode });
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=status]")).toHaveText(journey.sampleStatusAfterReport);
    await expect(row.locator("td[name=returnable]")).toHaveText("");
    await expect(row.locator("button[name=action_open_return]")).toHaveCount(0);
  });

  await step(staff, "SF-04-A3: The sample's own form offers no return either, and the sample stays retained", async () => {
    await openSample(staff);
    await expect(status(staff)).toHaveAttribute("data-value", "retained");
    await expect(returnButton(staff)).toHaveCount(0);
    sample.status = await shown(status(staff));
    handOver("SF-04", { sampleStatusAfterSf04: sample.status });
  });

  // business-flows.md SF-04 main path and SF-04-A3 start when the retention period is over; the journey cannot wait
  // for it, so the report shows both as not reached.
  await step(tester, "Main path: the retention period ends, the sample shows on the tester's daily to-do and she disposes of it by its method", async () => {
    expect.soft(sample.retainedUntil <= labDay(), `the retention period of ${journey.sampleLabCode} is over (it ends on ${iso(sample.retainedUntil)}; no click makes days pass)`).toBe(true);
  });

  await step(staff, "SF-04-A3: after its retention period, sample delivery staff return the sample to the customer and it ends returned", async () => {
    await expect.soft(returnButton(staff), `the sample offers Return once its retention period is over (on ${iso(sample.retainedUntil)})`).toHaveCount(1, { timeout: 1000 });
  });
});

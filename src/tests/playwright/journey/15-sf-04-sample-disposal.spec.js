import { expect, handOver, outside, received, step, test } from "../support/journey";
import { dated, field, labDay, listed, openListed, openMenu, search, settled, status } from "../support/odoo";

const SAMPLES = ["sol_laboratory.menu_laboratory_root", "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample"];

const ENGLISH_DAY = "mm/dd/yyyy";
const DAY = 24 * 60 * 60 * 1000;

const iso = (date) => date.toISOString().slice(0, 10);
const shown = async (locator) => (await locator.innerText()).trim();

test("SF-04 Sample retention, return and disposal", async ({ as }) => {
  const journey = received("tag", "sampleLabCode", "sampleType", "reportNumber");
  const sample = {};

  const tester = await as("demo.tester");

  await step(tester, "The issued report leaves the kept sample retained until the report day plus its sample type's retention days", async () => {
    await openMenu(tester, ...SAMPLES);
    await search(tester, journey.sampleLabCode);
    const row = listed(tester, journey.sampleLabCode);
    await expect(row).toHaveCount(1);
    await expect(row.locator("td[name=sample_type_id]")).toHaveText(journey.sampleType);
    await openListed(tester, journey.sampleLabCode);
    await expect(status(tester)).toHaveAttribute("data-value", "retained");
    const until = field(tester, "retained_until").locator("[data-tooltip]");
    await expect(until).toHaveAttribute("data-tooltip", /\d/);
    sample.retainedUntil = dated(await until.getAttribute("data-tooltip"), ENGLISH_DAY);
    sample.status = await shown(status(tester));
    await field(tester, "sample_type_id").locator("a").click();
    await settled(tester);
    await expect(field(tester, "name")).toHaveText(journey.sampleType);
    await expect(field(tester, "is_retained").locator("input")).toBeChecked();
    sample.retentionDays = Number(await shown(field(tester, "retention_days")));
    expect(sample.retentionDays).toBeGreaterThan(0);
    // The report was issued earlier in the journey, so its day is today or before, and the retention runs on.
    const reportDay = new Date(sample.retainedUntil.getTime() - sample.retentionDays * DAY);
    expect(reportDay <= labDay(), `the retention of ${journey.sampleLabCode} counts from the report day`).toBe(true);
    expect(sample.retainedUntil > labDay(), `the retention of ${journey.sampleLabCode} runs past today`).toBe(true);
    handOver("SF-04", { retentionEnds: iso(sample.retainedUntil), retentionDays: sample.retentionDays, sampleStatusAfterSf04: sample.status });
  });

  const after = `${sample.retentionDays} days after the report`;
  await outside("The sample's retention period ends", after);
  await outside("The daily job puts the sample on the tester's to-do", after);
  await outside("The tester disposes of the sample by its method and records when, by whom and how", after);
});

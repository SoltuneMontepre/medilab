import { expect, handOver, outside, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, press, search, status } from "../support/odoo";

const SAMPLES = ["sol_laboratory.menu_laboratory_root", "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample"];

const HEAD = "Hoang Van Minh";
const CATEGORIES = { raw: "Raw Data", result: "Results" };

test("SF-11 Laboratory file administration", async ({ as }) => {
  const journey = received("tag", "sampleLabCode", "department");
  const labCode = journey.sampleLabCode;
  const folders = {};

  const head = await as("demo.head_of_department");
  const ofCategory = (category) => head.locator(".o_data_row", { has: head.locator("td[name=category]", { hasText: new RegExp(`^${category}$`) }) });

  await step(head, "The head of department finds the received sample, which has no folders yet", async () => {
    await openMenu(head, ...SAMPLES);
    await search(head, labCode);
    await expect(listed(head, labCode)).toHaveCount(1);
    await openListed(head, labCode);
    await expect(field(head, "code")).toHaveText(labCode);
    await expect(status(head)).toHaveAttribute("data-value", "received");
    await expect(head.locator("button[name=action_open_laboratory_folders]:visible")).toHaveCount(0);
  });

  await step(head, "The head of department creates the sample's raw-data and result folders", async () => {
    await press(head, "action_create_laboratory_folders");
    // The pointer rests where the button was, now the Name column, whose tooltip would cover the first folder.
    await head.mouse.move(0, 0);
    await expect(head.locator(".o_data_row")).toHaveCount(2);
    for (const [key, category] of Object.entries(CATEGORIES)) {
      const folder = ofCategory(category);
      await expect(folder).toHaveCount(1);
      await expect(folder.locator("td[name=name]")).toContainText(labCode);
      await expect(folder.locator("td[name=status]")).toHaveText("In Use");
      await expect(folder.locator("td[name=owner_id]")).toHaveText(HEAD);
      await expect(folder.locator("td[name=sample_id]")).toHaveText(labCode);
      folders[key] = (await folder.locator("td[name=name]").innerText()).trim();
    }
    handOver("SF-11", { rawFolderName: folders.raw, resultFolderName: folders.result, folderOwner: HEAD });
  });

  await outside("The head of department, as the folders' owner, adds the tester as a member", "Medilab Sync");
  await outside("The tester binds the sample's folders", "Medilab Sync");
});

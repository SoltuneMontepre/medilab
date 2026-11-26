import { expect, handOver, received, step, test } from "../support/journey";
import { field, listed, openListed, openMenu, openTab, pick, press, pressLabel, save, search, status } from "../support/odoo";

const LABORATORY = "sol_laboratory.menu_laboratory_root";
const DOCUMENTS = "sol_laboratory.menu_laboratory_documents";
const SAMPLES = [LABORATORY, "sol_laboratory.menu_laboratory_samples", "sol_laboratory.menu_sample"];
const FOLDERS = [LABORATORY, DOCUMENTS, "sol_laboratory.menu_laboratory_folder"];
const FILES = [LABORATORY, DOCUMENTS, "sol_laboratory.menu_laboratory_file"];
const FOLDER_MEMBERS = [LABORATORY, DOCUMENTS, "sol_laboratory.menu_laboratory_folder_member"];

const HEAD = "Hoang Van Minh";
const CATEGORIES = { raw: "Raw Data", result: "Results" };

const createFolders = (page) => page.locator("button[name=action_create_laboratory_folders]:visible");
const sampleFolders = (page) => page.locator("button[name=action_open_laboratory_folders]:visible");
const members = (page) => field(page, "member_ids").locator(".o_data_row");
const newRecords = (page) => page.locator(".o_list_button_add:visible");

test("SF-11 Laboratory file administration", async ({ as }) => {
  const journey = received("tag", "sampleLabCode", "testerName");
  const labCode = journey.sampleLabCode;
  const tester = journey.testerName;
  const folders = {};

  const openSample = async (page) => {
    await openMenu(page, ...SAMPLES);
    await search(page, labCode);
    await expect(listed(page, labCode)).toHaveCount(1);
    await openListed(page, labCode);
    await expect(field(page, "code")).toHaveText(labCode);
  };

  const findFolders = async (page) => {
    await openMenu(page, ...FOLDERS);
    await search(page, labCode);
    await expect(page.locator(".o_data_row")).toHaveCount(2);
  };

  const ofCategory = (page, category) => page.locator(".o_data_row", { has: page.locator("td[name=category]", { hasText: new RegExp(`^${category}$`) }) });

  const expectMembers = async (page, ...rows) => {
    await openTab(page, "members");
    await expect(members(page)).toHaveCount(rows.length);
    for (const [index, [name, role]] of rows.entries()) {
      await expect(members(page).nth(index).locator("td[name=user_id]")).toHaveText(name);
      await expect(members(page).nth(index).locator("td[name=role]")).toHaveText(role);
    }
  };

  // The ways a browser could add a file to a sample's folder: a new line or an upload field on the folder's Files
  // tab, then a New button or an upload field on the Files list.
  const waysToAddFile = async (page) => {
    await openTab(page, "files");
    await expect(field(page, "file_ids").locator(".o_data_row")).toHaveCount(0);
    const onFolder = await page.locator(".o_field_widget[name=file_ids] .o_field_x2many_list_row_add, .o_action_manager input[type=file]").count();
    await openMenu(page, ...FILES);
    await search(page, labCode, { field: "Folder" });
    await expect(page.locator(".o_data_row")).toHaveCount(0);
    return onFolder + (await newRecords(page).count()) + (await page.locator(".o_action_manager input[type=file]").count());
  };

  const head = await as("demo.head_of_department");

  await step(head, "The head of department finds the received sample, which has no folders yet", async () => {
    await openSample(head);
    await expect(status(head)).toHaveAttribute("data-value", "received");
    await expect(sampleFolders(head)).toHaveCount(0);
    await expect(createFolders(head)).toBeVisible();
  });

  await step(head, "The head of department creates the sample's raw-data and result folders", async () => {
    await press(head, "action_create_laboratory_folders");
    // The pointer rests where the button was, now the Name column, whose tooltip would cover the first folder.
    await head.mouse.move(0, 0);
    await expect(head.locator(".o_data_row")).toHaveCount(2);
    for (const [key, category] of Object.entries(CATEGORIES)) {
      const folder = ofCategory(head, category);
      await expect(folder).toHaveCount(1);
      await expect(folder.locator("td[name=name]")).toContainText(labCode);
      await expect(folder.locator("td[name=status]")).toHaveText("In Use");
      await expect(folder.locator("td[name=owner_id]")).toHaveText(HEAD);
      await expect(folder.locator("td[name=sync_mode]")).toHaveText("Upload Only");
      await expect(folder.locator("td[name=sample_id]")).toHaveText(labCode);
      folders[key] = (await folder.locator("td[name=name]").innerText()).trim();
    }
    handOver("SF-11", { rawFolderName: folders.raw, resultFolderName: folders.result, folderOwner: (await ofCategory(head, CATEGORIES.raw).locator("td[name=owner_id]").innerText()).trim() });
  });

  await step(head, "The head of department, as the folders' owner, adds the tester as a member", async () => {
    await openListed(head, folders.raw);
    await expect(field(head, "name")).toHaveText(folders.raw);
    await expect(field(head, "owner_id")).toHaveText(HEAD);
    await expectMembers(head, [HEAD, "Owner"]);
    const onFolder = await field(head, "member_ids").locator(".o_field_x2many_list_row_add").count();
    await openMenu(head, ...FOLDER_MEMBERS);
    await search(head, labCode);
    await expect(head.locator(".o_data_row")).toHaveCount(2);
    await expect(listed(head, folders.raw).locator("td[name=role]")).toHaveText("Owner");
    await expect(listed(head, folders.result).locator("td[name=role]")).toHaveText("Owner");
    const onMembers = await newRecords(head).count();
    expect.soft(onFolder + onMembers, "The owner has a way to add a member on the folder's Members tab or the Folder Members list").toBeGreaterThan(0);
  });

  const lan = await as("demo.tester");

  await step(lan, "The tester, not yet a member, finds no folders on the sample", async () => {
    await openSample(lan);
    await expect(sampleFolders(lan)).toHaveCount(0);
    await expect(createFolders(lan)).toHaveCount(0);
  });

  const admin = await as("demo.administrator");

  await step(admin, "An administrator adds the tester as a member of the sample's folders", async () => {
    for (const folder of [folders.raw, folders.result]) {
      await findFolders(admin);
      await openListed(admin, folder);
      await expect(field(admin, "name").locator("input")).toHaveValue(folder);
      await openTab(admin, "members");
      await field(admin, "member_ids").locator(".o_field_x2many_list_row_add button").click();
      await expect(admin.locator(".modal:visible .o_form_view")).toBeVisible();
      await pick(admin, "user_id", tester);
      await pressLabel(admin, "Save & Close");
      await save(admin);
      await expectMembers(admin, [HEAD, "Owner"], [tester, "Member"]);
    }
  });

  await step(lan, "The tester browses the sample's folders in the back office", async () => {
    await openSample(lan);
    await expect(sampleFolders(lan).locator(".o_stat_value")).toHaveText("2");
    await press(lan, "action_open_laboratory_folders");
    await expect(lan.locator(".o_data_row")).toHaveCount(2);
    await expect(listed(lan, folders.raw).locator("td[name=status]")).toHaveText("In Use");
    await expect(listed(lan, folders.result).locator("td[name=status]")).toHaveText("In Use");
    await openListed(lan, folders.result);
    await expect(field(lan, "name")).toHaveText(folders.result);
    await expect(field(lan, "category")).toHaveText(CATEGORIES.result);
    await expectMembers(lan, [HEAD, "Owner"], [tester, "Member"]);
    await expect(field(lan, "member_ids").locator(".o_field_x2many_list_row_add")).toHaveCount(0);
    await openTab(lan, "files");
    await expect(field(lan, "file_ids").locator(".o_data_row")).toHaveCount(0);
  });

  await step(lan, "The tester saves a result file in the sample's folder from the browser", async () => {
    expect.soft(await waysToAddFile(lan), "The tester has a way to add a file to the sample's folder from the browser").toBeGreaterThan(0);
  });

  await step(head, "The head of department saves a file in the sample's folder from the browser", async () => {
    await findFolders(head);
    await openListed(head, folders.raw);
    expect.soft(await waysToAddFile(head), "The head of department has a way to add a file to the sample's folder from the browser").toBeGreaterThan(0);
  });

  await step(admin, "An administrator turns the result folder off", async () => {
    await expect(field(admin, "name").locator("input")).toHaveValue(folders.result);
    await press(admin, "action_turn_off");
    await expect(admin.locator(".modal:visible .modal-body")).toContainText("Nobody can upload to the folder until it is turned on again; its members still read it.");
    await pressLabel(admin, "Ok");
    await expect(status(admin)).toHaveAttribute("data-value", "turned_off");
    await expect(admin.locator("button[name=action_turn_on]:visible")).toBeVisible();
    await expect(admin.locator("button[name=action_turn_off]:visible")).toHaveCount(0);
  });

  await step(lan, "The tester, a member, still reads the turned-off folder", async () => {
    await findFolders(lan);
    await expect(listed(lan, folders.raw).locator("td[name=status]")).toHaveText("In Use");
    await expect(listed(lan, folders.result).locator("td[name=status] .badge")).toHaveText("Turned Off");
    await expect(listed(lan, folders.result).locator("td[name=status] .badge")).toHaveClass(/text-bg-danger/);
    await openListed(lan, folders.result);
    await expect(status(lan)).toHaveAttribute("data-value", "turned_off");
    await expectMembers(lan, [HEAD, "Owner"], [tester, "Member"]);
    await expect(lan.locator("button[name=action_turn_on]:visible, button[name=action_turn_off]:visible, button[name=action_archive_folder]:visible")).toHaveCount(0);
  });

  await step(admin, "The administrator turns the folder on, which restores its availability", async () => {
    await press(admin, "action_turn_on");
    await expect(status(admin)).toHaveAttribute("data-value", "in_use");
    await expect(admin.locator("button[name=action_turn_off]:visible")).toBeVisible();
    await expect(admin.locator("button[name=action_turn_on]:visible")).toHaveCount(0);
  });

  await step(head, "The sample's folders are in use, owned by the head of department, with the tester as member", async () => {
    await openSample(head);
    await expect(createFolders(head)).toHaveCount(0);
    await expect(sampleFolders(head).locator(".o_stat_value")).toHaveText("2");
    const shown = {};
    for (const folder of [folders.raw, folders.result]) {
      await press(head, "action_open_laboratory_folders");
      await expect(head.locator(".o_data_row")).toHaveCount(2);
      await expect(listed(head, folder).locator("td[name=status]")).toHaveText("In Use");
      await expect(listed(head, folder).locator("td[name=owner_id]")).toHaveText(HEAD);
      await openListed(head, folder);
      await expect(status(head)).toHaveAttribute("data-value", "in_use");
      await expectMembers(head, [HEAD, "Owner"], [tester, "Member"]);
      shown[folder] = (await members(head).locator("td[name=user_id]").allInnerTexts()).map((name) => name.trim());
      await head.locator(".o_breadcrumb a", { hasText: labCode }).click();
      await expect(field(head, "code")).toHaveText(labCode);
    }
    expect(shown[folders.result]).toEqual(shown[folders.raw]);
    handOver("SF-11", { folderMembers: shown[folders.raw] });
  });
});

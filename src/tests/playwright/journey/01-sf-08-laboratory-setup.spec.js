import { expect, handOver, startJourney, step, test } from "../support/journey";
import { addLine, addRow, choose, field, labDay, listed, newRecord, openListed, openMenu, openRow, openTab, pick, save, search, status, tick, type, typeDate } from "../support/odoo";
import { openHeader, send } from "../support/portal";

const MASTER_DATA = "sol_laboratory.menu_master_data_root";
const CATALOG = "sol_laboratory.menu_master_data_catalog";
const MACHINES = ["sol_laboratory.menu_master_data_machines", "sol_laboratory.menu_machine"];

const METHOD = "LAB-CR6-01";
const SAMPLE_TYPE = "Bottled water";
const DEMO_MACHINE = "UVVIS-01";
const JOURNEY_MACHINE = "UVVIS-JOURNEY";
const TESTER = "Dang Thi Lan";
const PRICE = 180000;

// The day the open machine's calibration is due, which the form writes like "Nov 26, 2027", without the year for a
// day of this year; nothing for a machine without calibration.
async function calibratedUntil(page) {
  const shown = (await field(page, "next_calibration_date").innerText()).trim();
  if (!shown) return null;
  const [day, year = labDay().getUTCFullYear()] = shown.split(", ");
  return new Date(`${day}, ${year} UTC`);
}

test("SF-08 Laboratory setup", async ({ as }) => {
  const tag = startJourney();
  const parameterName = `Journey nitrate ${tag}`;
  const admin = await as("demo.administrator");

  await step(admin, "The administrator adds the test parameter with its group and way of testing", async () => {
    await openMenu(admin, MASTER_DATA, CATALOG, "sol_laboratory.menu_test_parameter");
    await newRecord(admin);
    await type(admin, "name", parameterName);
    await pick(admin, "group_ids", "Physicochemical");
    await pick(admin, "main_group_id", "Physicochemical");
    const way = await addLine(admin, "method_ids");
    await pick(admin, "method_id", METHOD, way);
    await pick(admin, "department_id", "Chemistry", way);
    await type(admin, "turnaround_days", 3, way);
    // The applicability below can only name a way that is saved.
    await save(admin);
    await expect(field(admin, "code").locator("input")).toHaveValue(/\S/);
    const saved = field(admin, "method_ids").locator(".o_data_row");
    await expect(saved).toHaveCount(1);
    handOver("SF-08", {
      parameterName,
      parameterCode: await field(admin, "code").locator("input").inputValue(),
      methodCode: (await saved.locator("td[name=method_id]").innerText()).trim(),
    });
  });

  await step(admin, "The administrator records the sample type the parameter applies to, with its unit and detection limits", async () => {
    await openTab(admin, "sample_types");
    const applicability = await addLine(admin, "applicability_ids");
    await pick(admin, "sample_type_id", SAMPLE_TYPE, applicability);
    await pick(admin, "parameter_method_id", METHOD, applicability);
    await pick(admin, "unit_id", "mg/L", applicability);
    await type(admin, "lod", "0.05", applicability);
    await type(admin, "loq", "0.15", applicability);
    await type(admin, "result_decimals", 2, applicability);
    await tick(admin, "is_default", true, applicability);
    await save(admin);
    await expect(field(admin, "sample_type_ids")).toContainText(SAMPLE_TYPE);
    handOver("SF-08", { sampleType: SAMPLE_TYPE });
  });

  await step(admin, "The administrator sets the price and tax of the parameter", async () => {
    await openTab(admin, "price");
    const price = await addLine(admin, "price_ids");
    await type(admin, "list_price", PRICE, price);
    await pick(admin, "tax_id", "VAT 10%", price);
    await save(admin);
    await expect(field(admin, "price_ids").locator(".o_data_row")).toContainText("180,000");
    handOver("SF-08", { price: PRICE });
  });

  await step(admin, "The administrator makes sure the testing method states its sampling requirement for the sample type", async () => {
    await openMenu(admin, MASTER_DATA, CATALOG, "sol_laboratory.menu_testing_method");
    await openRow(admin, METHOD);
    handOver("SF-08", { methodName: await field(admin, "name").locator("input, textarea").first().inputValue() });
    await openTab(admin, "sampling_requirements");
    const requirements = field(admin, "sampling_requirement_ids").locator(".o_data_row");
    if (!(await requirements.filter({ hasText: SAMPLE_TYPE }).count())) {
      const requirement = await addLine(admin, "sampling_requirement_ids");
      await pick(admin, "sample_type_id", SAMPLE_TYPE, requirement);
      await type(admin, "amount", 100, requirement);
      await pick(admin, "unit_id", "mL", requirement);
      await type(admin, "container_type", "Polyethylene bottle", requirement);
      await type(admin, "preservation", "Acidified with HNO₃ to pH below 2", requirement);
      await save(admin);
    }
    await expect(requirements.filter({ hasText: SAMPLE_TYPE })).toContainText("Polyethylene bottle");
  });

  await step(admin, "The administrator makes sure two calibrated machines in use run the testing method", async () => {
    for (const machine of [DEMO_MACHINE, JOURNEY_MACHINE]) {
      await openMenu(admin, MASTER_DATA, ...MACHINES);
      await search(admin, machine);
      if (await listed(admin, machine).count()) {
        await openListed(admin, machine);
      } else {
        expect(machine, `${DEMO_MACHINE} is demo data`).toBe(JOURNEY_MACHINE);
        await newRecord(admin);
        await type(admin, "name", "UV-Vis spectrophotometer (journey)");
        await type(admin, "code", JOURNEY_MACHINE);
        await pick(admin, "location_id", "P101-B2");
        await openTab(admin, "methods");
        const link = await addLine(admin, "method_ids");
        await pick(admin, "method_id", METHOD, link);
        await type(admin, "duration_minutes", 60, link);
        await type(admin, "capacity", 1, link);
      }
      const calibrated = async () => (await calibratedUntil(admin)) >= labDay({ days: 30 });
      if (!(await calibrated())) {
        await openTab(admin, "services");
        const calibration = await addLine(admin, "service_ids");
        await choose(admin, "kind", "Calibration", calibration);
        await typeDate(admin, "service_date", labDay(), calibration);
        await typeDate(admin, "next_due_date", labDay({ years: 1 }), calibration);
        await type(admin, "performed_by", "Quatest 1", calibration);
      }
      await save(admin);
      await expect(field(admin, "code").locator("input")).toHaveValue(machine);
      await expect(status(admin)).toHaveText("In use");
      expect(await calibrated(), "calibration valid for the next 30 days").toBe(true);
      await openTab(admin, "methods");
      await expect(field(admin, "method_ids").locator(".o_data_row", { hasText: METHOD })).toContainText("60");
    }
    handOver("SF-08", { machineCodes: [DEMO_MACHINE, JOURNEY_MACHINE] });
  });

  const labHead = await as("demo.lab_head");
  await step(labHead, "The Lab Head authorizes the tester for the parameter", async () => {
    await openMenu(labHead, MASTER_DATA, CATALOG, "sol_laboratory.menu_parameter_authorization");
    const authorization = await addRow(labHead);
    await pick(labHead, "person_id", TESTER, authorization);
    await pick(labHead, "parameter_id", parameterName, authorization);
    await save(labHead);
    await search(labHead, parameterName, { field: "Parameter" });
    const rows = labHead.locator(".o_data_row");
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText(TESTER);
    handOver("SF-08", { testerName: (await rows.locator("td[name=person_id]").innerText()).trim() });
  });

  const customer = await as("demo.customer");
  await step(customer, "A customer finds the parameter with its price in the catalog", async () => {
    await openHeader(customer, "/catalog");
    await customer.locator("select[name=sample_type]").selectOption({ label: SAMPLE_TYPE });
    await customer.locator("input[name=name]").fill(parameterName);
    await send(customer, "/catalog");
    const offered = customer.locator("main tbody tr", { hasText: parameterName });
    await expect(offered).toHaveCount(1);
    await expect(offered).toContainText("180,000");
  });
});

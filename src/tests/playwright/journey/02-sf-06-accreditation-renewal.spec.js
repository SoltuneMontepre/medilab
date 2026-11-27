import { expect, handOver, received, step, test } from "../support/journey";
import { addLine, field, labDay, newRecord, openMenu, openRow, openTab, pick, press, save, type, typeDate } from "../support/odoo";

const MASTER_DATA = "sol_laboratory.menu_master_data_root";
const CATALOG = "sol_laboratory.menu_master_data_catalog";
const TEST_PARAMETERS = [MASTER_DATA, CATALOG, "sol_laboratory.menu_test_parameter"];

test("SF-06 Accreditation and registration renewal", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "sampleType");
  const certificateCode = `VILAS ${journey.tag}`;
  const validUntil = labDay({ years: 3 });
  const admin = await as("demo.administrator");

  await step(admin, "The administrator records the accreditation certificate the laboratory received", async () => {
    await openMenu(admin, MASTER_DATA, CATALOG, "sol_laboratory.menu_accreditation_certificate");
    await newRecord(admin);
    await type(admin, "code", certificateCode);
    await type(admin, "issuing_body", "Bureau of Accreditation (BoA)");
    await typeDate(admin, "valid_from", labDay());
    await typeDate(admin, "valid_until", validUntil);
    await save(admin);
    await expect(admin.locator(".o_last_breadcrumb_item")).toHaveText(certificateCode);
    handOver("SF-06", { certificateCode });
  });

  await step(admin, "The administrator imports the scope line identifying the method, the parameter and the sample type", async () => {
    await press(admin, "action_import_scope");
    await pick(admin, "field_id", "Chemistry");
    const line = await addLine(admin, "line_ids");
    await type(admin, "code", journey.methodCode, line);
    await pick(admin, "parameter_ids", journey.parameterName, line);
    await pick(admin, "sample_type_ids", journey.sampleType, line);
    await press(admin, "action_import");
    const scope = field(admin, "scope_line_ids").locator(".o_data_row");
    await expect(scope).toHaveCount(1);
    await expect(scope.locator("td[name=method_id]")).toHaveText(journey.methodCode);
    await expect(scope).toContainText(journey.parameterName);
    await expect(scope).toContainText(journey.sampleType);
    await expect(scope.locator("td[name=to_confirm] input")).not.toBeChecked();
  });

  await step(admin, "The in-house way of the parameter is accredited on the sample type", async () => {
    await openMenu(admin, ...TEST_PARAMETERS);
    await openRow(admin, journey.parameterName);
    await openTab(admin, "sample_types");
    const applicability = field(admin, "applicability_ids").locator(".o_data_row", { hasText: journey.sampleType });
    await expect(applicability.locator("td[name=is_accredited] input")).toBeChecked();
  });
});

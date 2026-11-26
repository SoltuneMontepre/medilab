import { expect, handOver, received, step, test } from "../support/journey";
import { addLine, discard, field, labDay, newRecord, openMenu, openRow, openTab, pick, press, save, suggested, type, typeDate } from "../support/odoo";

const MASTER_DATA = "sol_laboratory.menu_master_data_root";
const CATALOG = "sol_laboratory.menu_master_data_catalog";
const TEST_PARAMETERS = [MASTER_DATA, CATALOG, "sol_laboratory.menu_test_parameter"];
const SUBCONTRACTORS = [MASTER_DATA, "sol_laboratory.menu_subcontractor"];

const SUBCONTRACTOR = "Northern Testing Laboratory";

const iso = (date) => date.toISOString().slice(0, 10);

test("SF-06 Accreditation and registration renewal", async ({ as }) => {
  const journey = received("tag", "parameterName", "methodCode", "sampleType");
  const certificateCode = `VILAS ${journey.tag}`;
  const renewedUntil = labDay({ years: 3 });
  const admin = await as("demo.administrator");

  // What a new way of testing of the journey's parameter offers as subcontractor, on a line that is not saved.
  const offeredSubcontractors = async () => {
    await openMenu(admin, ...TEST_PARAMETERS);
    await openRow(admin, journey.parameterName);
    const way = await addLine(admin, "method_ids");
    return (await suggested(admin, "subcontractor_id", SUBCONTRACTOR, way)).filter({ hasText: SUBCONTRACTOR });
  };

  await step(admin, "The administrator records the accreditation certificate the laboratory received", async () => {
    await openMenu(admin, MASTER_DATA, CATALOG, "sol_laboratory.menu_accreditation_certificate");
    await newRecord(admin);
    await type(admin, "code", certificateCode);
    await type(admin, "issuing_body", "Bureau of Accreditation (BoA)");
    await typeDate(admin, "valid_from", labDay());
    await typeDate(admin, "valid_until", renewedUntil);
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

  await step(admin, "The subcontractor's accreditation expires and it cannot be chosen", async () => {
    await openMenu(admin, ...SUBCONTRACTORS);
    await openRow(admin, SUBCONTRACTOR);
    await typeDate(admin, "accreditation_expiry", labDay({ days: -1 }));
    await save(admin);
    await expect(await offeredSubcontractors()).toHaveCount(0);
  });

  await step(admin, "The administrator renews the subcontractor's accreditation and it can be chosen again", async () => {
    await discard(admin);
    await openMenu(admin, ...SUBCONTRACTORS);
    await openRow(admin, SUBCONTRACTOR);
    await typeDate(admin, "accreditation_expiry", renewedUntil);
    await save(admin);
    await expect(field(admin, "accreditation_expiry")).toContainText(String(renewedUntil.getUTCFullYear()));
    handOver("SF-06", {
      subcontractorName: await field(admin, "name").locator("input").inputValue(),
      subcontractorValidUntil: iso(renewedUntil),
    });
    await expect(await offeredSubcontractors()).toHaveCount(1);
  });
  await discard(admin);
});

const vscode = require("vscode");
const fs = require("node:fs");
const path = require("node:path");

// Retry once a second while OdooLS indexes, until a definition ends with the target path.
async function definitions(uri, position, target, attempts) {
  const locations = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", uri, position) || [];
  if (attempts <= 1 || locations.some(item => (item.targetUri || item.uri).fsPath.endsWith(target))) return locations;
  await new Promise(resolve => setTimeout(resolve, 1000));
  return definitions(uri, position, target, attempts - 1);
}

async function checkDefinition(root, {name, path: file, needle, offset, target}, positions, report) {
  const uri = vscode.Uri.file(path.join(root, file));
  const document = await vscode.workspace.openTextDocument(uri);
  await vscode.window.showTextDocument(document);
  const position = document.positionAt(document.getText().indexOf(needle) + offset);
  positions[name] = {uri, position};
  const locations = await definitions(uri, position, target, 90);
  if (!locations.some(item => (item.targetUri || item.uri).fsPath.endsWith(target))) {
    throw new Error(`Definition did not resolve for ${name} in ${file}`);
  }
  report.definitions.push({name, file, line: position.line, character: position.character, targets: locations.map(item => (item.targetUri || item.uri).fsPath)});
}

exports.activate = async function () {
  const root = vscode.workspace.workspaceFolders[0].uri.fsPath;
  const output = path.join(root, ".local/verification/cursor-editor.json");
  const report = { workspace: root, verified: false, definitions: [] };
  try {
    const odoo = vscode.extensions.getExtension("Odoo.odoo");
    if (!odoo) throw new Error("Official Odoo extension is not installed.");
    await odoo.activate();
    report.extension_version = odoo.packageJSON.version;
    const cases = JSON.parse(fs.readFileSync(path.join(__dirname, "../../odoo_intelligence/navigation_cases.json"), "utf8"));
    const positions = {};
    // Check the cases one after another, so each editor is shown before its definition is requested.
    await cases.reduce((previous, item) => previous.then(() => checkDefinition(root, item, positions, report)), Promise.resolve());
    const {uri: fieldUri, position: fieldPosition} = positions.custom_field;
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(fieldUri), {preview: false});
    const hover = await vscode.commands.executeCommand("vscode.executeHoverProvider", fieldUri, fieldPosition);
    report.hover = hover.map(item => item.contents.map(content => typeof content === "string" ? content : content.value));
    if (!JSON.stringify(report.hover).includes("ParameterGroup")) throw new Error("Odoo relation hover did not resolve.");
    const completion = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", fieldUri, fieldPosition);
    if (!completion.items.some(item => (item.label.label || item.label) === "main_group_id")) {
      throw new Error("Odoo field completion did not resolve.");
    }
    report.completion = "main_group_id";
    report.verified = true;
  } catch (error) {
    report.error = String(error.stack || error);
  } finally {
    fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
    // The runner must provide an isolated user-data directory so this quits only its test instance.
    setTimeout(() => vscode.commands.executeCommand("workbench.action.quit"), 500);
  }
};

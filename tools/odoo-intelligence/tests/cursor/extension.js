const vscode = require("vscode");
const fs = require("node:fs");
const path = require("node:path");

exports.activate = async function () {
  const root = vscode.workspace.workspaceFolders[0].uri.fsPath;
  const output = path.join(root, ".local/verification/cursor-editor.json");
  const report = { workspace: root, verified: false, definitions: [] };
  try {
    const odoo = vscode.extensions.getExtension("Odoo.odoo");
    if (!odoo) throw new Error("Official Odoo extension is not installed.");
    await odoo.activate();
    report.extension_version = odoo.packageJSON.version;
    const cases = [
      ["src/core/modules/sol_commerce/models/invoicing/payment_transaction.py", 193, 33, "/base/models/ir_sequence.py"],
      ["src/core/modules/sol_commerce/models/invoicing/payment_transaction.py", 116, 27, "/invoicing/reconciliation_day.py"],
      ["src/core/modules/sol_laboratory/models/master_data/test_parameter.py", 58, 27, "/master_data/test_parameter.py"],
      ["src/core/modules/sol_commerce/models/invoicing/account_move.py", 51, 42, "/account/models/account_move.py"],
      ["src/core/modules/sol_laboratory/views/master_data/test_parameter_views.xml", 9, 31, "/master_data/test_parameter.py"],
    ];
    for (const [file, line, character, suffix] of cases) {
      const uri = vscode.Uri.file(path.join(root, file));
      const document = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(document);
      const position = new vscode.Position(line, character);
      let locations = [];
      for (let attempt = 0; attempt < 90; attempt++) {
        locations = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", uri, position) || [];
        if (locations.some(item => (item.targetUri || item.uri).fsPath.endsWith(suffix))) break;
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      if (!locations.some(item => (item.targetUri || item.uri).fsPath.endsWith(suffix))) {
        throw new Error(`Definition did not resolve for ${file}:${line}:${character}`);
      }
      report.definitions.push({file, line, character, targets: locations.map(item => (item.targetUri || item.uri).fsPath)});
    }
    const fieldUri = vscode.Uri.file(path.join(root, cases[2][0]));
    const fieldPosition = new vscode.Position(58, 27);
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(fieldUri), {preview: false});
    const hover = await vscode.commands.executeCommand("vscode.executeHoverProvider", fieldUri, fieldPosition);
    report.hover = hover.map(item => item.contents.map(content => typeof content === "string" ? content : content.value));
    if (!JSON.stringify(report.hover).includes("ParameterGroup")) throw new Error("Odoo relation hover did not resolve.");
    report.hover = hover.map(item => item.contents.map(content => typeof content === "string" ? content : content.value));
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

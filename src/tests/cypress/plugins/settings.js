function settingsTasks(call) {
  const checkpoints = new Map();
  let nextCheckpoint = 0;

  async function parameters(login) {
    return call({ login, model: "ir.config_parameter", method: "search_read", args: [[]], kwargs: { fields: ["key", "value"] } });
  }

  async function checkpoint({ login }) {
    try {
      const id = ++nextCheckpoint;
      checkpoints.set(id, { login, parameters: await parameters(login) });
      return id;
    } catch {
      throw new Error("The settings checkpoint could not be created.");
    }
  }

  // Settings Save writes every configured field. Keep complete values in Node, including credentials, out of browser logs.
  async function restore({ checkpoint: id }) {
    const saved = checkpoints.get(id);
    if (!saved) throw new Error("The settings checkpoint is unavailable.");
    try {
      const original = new Map(saved.parameters.map(({ key, value }) => [key, value]));
      const current = await parameters(saved.login);
      const present = new Map(current.map((parameter) => [parameter.key, parameter]));
      for (const [key, value] of original) {
        const parameter = present.get(key);
        if (!parameter) {
          await call({ login: saved.login, model: "ir.config_parameter", method: "create", args: [{ key, value }] });
        } else if (parameter.value !== value) {
          await call({ login: saved.login, model: "ir.config_parameter", method: "write", args: [[parameter.id], { value }] });
        }
      }
      const added = current.filter(({ key }) => !original.has(key)).map(({ id }) => id);
      if (added.length) await call({ login: saved.login, model: "ir.config_parameter", method: "unlink", args: [added] });
      const restored = await parameters(saved.login);
      if (restored.length !== original.size || restored.some(({ key, value }) => !original.has(key) || original.get(key) !== value)) {
        throw new Error("Settings verification failed.");
      }
      checkpoints.delete(id);
      return null;
    } catch {
      throw new Error("The settings checkpoint could not be restored.");
    }
  }

  return { odooCheckpointSettings: checkpoint, odooRestoreSettings: restore };
}

module.exports = { settingsTasks };

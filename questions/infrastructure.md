# Infrastructure questions

- **Server A size.** What CPU, memory and disk does VPS SSD LINUX 8 (`soltune-xoha`) have? Server B already uses 3.58 of its 4 GiB, so Server A may need to carry most of the load.
- **Sync app address and updates.** Which Odoo address is built into the sync app for production, set as the `MEDILAB_SYNC_ODOO_URL` Actions variable? Is the Tauri update signing key whose public key is in `tauri.conf.json` still available, and should Odoo serve update manifests at `/api/sync/v1/updates`, so that releases can update installed apps?
- **Recovery target.** How long may the system be down when a site is lost, and how many seconds of writes may be lost?
- **Rollback after a migration.** When a release upgrades the modules and then fails, should `cd-core` also restore the database from the pre-release backup, losing writes made since, or leave the newer schema for a person to decide?
- **Maintenance notice.** Are users told before a release window, such as by a banner or an email, and how long before? This applies in `window` mode.

## Related documents

- [Architecture](../docs/infrastructure/architecture.md)

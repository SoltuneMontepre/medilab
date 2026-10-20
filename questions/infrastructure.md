# Infrastructure questions

- **Sites and providers.** Which provider and city hosts each data site, and where does the witness run? The latency between the two data sites decides how long each write waits for the other site.
- **Deploying to the cluster.** Which tool applies the cluster manifests from the repository: FluxCD, Argo CD, or a pipeline step?
- **Object storage.** Which object storage holds attachments, such as Cloudflare R2 or Amazon S3, and how is it backed up?
- **IoT devices.** Are MQTT devices such as SIM7600 thermometers in scope? They cannot reach the system through Cloudflare Tunnel, so they would connect to each site's IP directly with a broker per site.
- **Sync app address and updates.** Which Odoo address is built into the sync app for production, set as the `MEDILAB_SYNC_ODOO_URL` Actions variable? Is the Tauri update signing key whose public key is in `tauri.conf.json` still available, and should Odoo serve update manifests at `/api/sync/v1/updates`, so that releases can update installed apps?
- **Recovery target.** How long may the system be down when a site is lost, and how many seconds of writes may be lost?

## Related documents

- [Architecture](../docs/infrastructure/architecture.md)

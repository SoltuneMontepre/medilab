# Infrastructure questions

- **Sites and providers.** Which provider and city hosts each data site, and where does the witness run? The latency between the two data sites decides how long each write waits for the other site.
- **Deploying to the cluster.** Which tool applies the cluster manifests from the repository: FluxCD, Argo CD, or a pipeline step?
- **Object storage.** Which object storage holds attachments, such as Cloudflare R2 or Amazon S3, and how is it backed up?
- **IoT devices.** Are MQTT devices such as SIM7600 thermometers in scope? They cannot reach the system through Cloudflare Tunnel, so they would connect to each site's IP directly with a broker per site.
- **Recovery target.** How long may the system be down when a site is lost, and how many seconds of writes may be lost?
- **AI tooling in CI.** `task ai:test` runs only on developer machines. Should a pipeline run it on pull requests that change `tools/odoo-intelligence`, without the live OdooLS tests that need `task ai:setup`?

## Related documents

- [Architecture](../docs/infrastructure/architecture.md)
- [Odoo intelligence](../docs/workflows/odoo-intelligence.md)

# Infrastructure questions

- **Bucket names.** What are the names of the main and backup buckets in Object Storage Lite? The architecture calls them `filestore` and `backups`; k3s needs the backup bucket's name to send etcd snapshots there, and `infra/cluster/` uses both names.
- **Sync app address and updates.** Which Odoo address is built into the sync app for production, set as the `MEDILAB_SYNC_ODOO_URL` Actions variable? Is the Tauri update signing key whose public key is in `tauri.conf.json` still available, and should Odoo serve update manifests at `/api/sync/v1/updates`, so that releases can update installed apps?
- **Recovery target.** How long may the system be down when a site is lost, and how many seconds of writes may be lost?
- **Rollback after a migration.** When a release upgrades the modules and then fails, should `cd-core` also restore the database from the pre-release backup, losing writes made since, or leave the newer schema for a person to decide?
- **Maintenance notice.** Are users told before a release window, such as by a banner or an email, and how long before? This applies in `window` mode.
- **MediLab image access.** `ghcr.io/soltunemontepre/medilab` cannot be pulled without credentials. Should the package be made public, like the repository, or should the cluster get a pull token from Doppler?
- **Doppler scope of the cluster.** External Secrets reads the whole `infra` config, which also holds `ANSIBLE_SSH_PRIVATE_KEY` and `K3S_TOKEN`. Should the secrets the cluster reads move to their own config, so that the cluster's token cannot reach the nodes?
- **Filestore storage.** Odoo's filestore is the `filestore` bucket mounted through an S3 CSI driver with GeeseFS. Is a filesystem mount acceptable, or should an Odoo module store attachments in the bucket through its API, with `boto3`, which is already a dependency?
- **Web host name.** Is `lims.soltunemontepre.tech` the production host name of Odoo?
- **Ansible approver.** Who must approve a `cd-ansible` apply? Terraform's `ansible_apply_reviewers` names `hatohui`, the account this was set up from; should it be someone else, or more than one person?
- **SSH from anywhere.** GitHub-hosted runners have no fixed addresses, so port 22 of every node is open to the internet with key-only login for `ansible`. Is that acceptable, or should the runs go through a self-hosted runner or a fixed-address network instead?
- **Password logins on the nodes.** Does anyone log in to Server A with a password? `ssh_hardening_enabled` is turned on once nobody does.

## Related documents

- [Architecture](../docs/infrastructure/architecture.md)

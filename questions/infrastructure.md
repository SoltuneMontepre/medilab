# Infrastructure questions

- **Server A size.** What CPU, memory and disk does VPS SSD LINUX 8 (`soltune-xoha`) have? Server B already uses 3.58 of its 4 GiB, so Server A may need to carry most of the load.
- **Recovery target.** How long may the system be down when a site is lost, and how many seconds of writes may be lost?
- **Rollback after a migration.** When a release upgrades the modules and then fails, should `cd-core` also restore the database from the pre-release backup, losing writes made since, or leave the newer schema for a person to decide?
- **Release check.** Is a 200 from `/web/health` within 10 minutes enough to call a release healthy, or should `verify` also log in or open a page?

## Related documents

- [Architecture](../docs/infrastructure/architecture.md)

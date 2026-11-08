# Sessions

## Goal

A person stays signed in when a release switches Odoo to its new colour, and when a request reaches another worker or replica. Odoo keeps sessions as files on the pod's disk, which the new colour and the other replicas cannot read.

## Design

- The Medilab Sessions module (`sol_session`) keeps every session as a row of the `sol_http_session` table in the database Odoo serves: its id, its data as JSON and when it was last saved.
- It is loaded with the server through `server_wide_modules` in `odoo.conf`, so its post-load hook replaces Odoo's file store before the first request. It needs `db_name` to name exactly one database, as production's does; otherwise sessions stay in files and Odoo logs a warning.
- The store keeps Odoo's behaviour: an unknown or invalid session id gives a new session, and saving a session again replaces its data. Signing out deletes the row, and rotating a session id saves the new one as Odoo does.
- Revoking a device deletes the sessions whose first 42 characters match its identifier, as Odoo's file store does. Odoo's daily autovacuum deletes sessions not saved for the inactivity limit.
- The first use in each process creates the table and its indexes when missing, under an advisory lock so workers starting together do not race. The table is not an Odoo model, so it has no fields, views or permissions. Uninstalling the module does not drop it.
- Each read and save takes a cursor from Odoo's connection pool, alongside the request's own, within `db_maxconn`.

## Related documents

- [Cluster](../infrastructure/cluster.md#odoo)
- [Architecture](../infrastructure/architecture.md#odoo)

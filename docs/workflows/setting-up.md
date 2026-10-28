# Setting up

Install and configure a laboratory. Each step says what to check before the next.

## Steps

1. **Odoo.** Install Odoo 20 Community. Add the MediLab modules and update the app list.
2. **Laboratory.** Install Laboratory on its own. Check: the catalog, people and Tasks menus open, and signing in as the administrator reaches them.
3. **Company.** Set the company name, address, logo and time zone to Asia/Ho_Chi_Minh. Sample-test due dates and the days accreditation certificates are valid use this time zone.
4. **Languages.** Install Vietnamese and set it on the users who work in it.
5. **E-commerce and Inventory.** Install either or both on top of Laboratory. Each runs without the other. Set the company country to Vietnam and load the Vietnamese accounting chart before issuing invoices; E-commerce does not issue them through an e-invoice provider.
6. **Settings.** Settings, under the Laboratory app's Configuration menu or in Odoo's Settings app, opens one block per installed MediLab module. Laboratory holds the safety margin and Code formats. A missing value falls back to its default.
7. **Code formats.** Code formats lists the `medilab.*` sequences. Change a prefix or padding there; codes already given keep their value.
8. **Digital signing.** Set `VIETTEL_SIGN_CLIENT_ID`, `VIETTEL_SIGN_CLIENT_SECRET`, `VIETTEL_SIGN_PROFILE_ID` and `VIETTEL_SIGN_USER_ID` in the Odoo server's environment, for a Viettel Sign account that signs without confirmation in the MySign app. Turn Digital signing on in the Laboratory settings, open Certificates and refresh them. Check: the laboratory's certificate is listed as valid with its expiry.
9. **Demo data.** Install the demo module only on a database used for trying the system. It is not part of a laboratory's installation.

A fresh installation works with the defaults: every setting has one, and only what the laboratory wants to change needs a visit to the settings screen.

## Local demo setup

- `task setup` keeps the standard local upgrade flow and uses the worktree's existing database and storage.
- If `task setup` has already created ordinary project resources, select a new project before running `task setup:fresh`. The fresh bootstrap refuses those existing resources; selection chooses available ports and leaves the ordinary project intact.
- Select the first isolated demo environment with `task setup:fresh:select PROJECT=medilab-bootstrap-<name>` before `task setup:fresh`. Initial selection refuses any existing resources, saves a new owner and host ports in `.local/demo-bootstrap.json` and `tools/infrastructure/.env`, and leaves other Compose projects untouched. Each port keeps its default (Odoo 8069, Postgres 15432, Garage 3900 and 3903, CloudBeaver 8978) when no socket holds it and no container of the selected engine publishes it, running or stopped; otherwise it gets such a free port between 20000 and 32767, below the ranges the operating system hands out and reserves dynamically. Selecting the same saved project again only verifies its identity; selecting a different project through `select` is refused. To use a second project after completing the first, run `task setup:fresh:switch PROJECT=medilab-bootstrap-<name>`. It verifies the completed current project and that the new identity owns no resources, then saves the previous marker under `.local/demo-bootstrap-selections/`. If a guarded reset later gives the same project a new owner, the older archive remains historical and the new owner gets a separate archive; only an archive whose owner and volumes match current resources can be selected. The same command can select a saved, completed project again after checking its owner and volumes. An incomplete project cannot be switched away. If switching is interrupted, Compose commands refuse the pending journal until `task setup:fresh:switch:recover` verifies both projects and restores a consistent selection. Read `MEDILAB_ODOO_PORT` from the saved `.env` for the browser URL. A selected project remains the target of subsequent Task commands from this worktree.
- `task setup:fresh` is only for a new local demo environment. It refuses to adopt any existing project resources, creates owner-validated persistent volumes and a project-specific Odoo image using the saved identity, initializes `base`, sets the company country to Vietnam, installs `l10n_vn`, and verifies the Vietnamese chart before installing MediLab modules. It then installs modules in explicit bootstrap mode, seeds demo data while a private HTTP asset server is available, and hands the same project and volumes to the normal application. It uses local development credentials and does not authenticate through Doppler.
- After a successful bootstrap, rerunning `task setup:fresh` starts the same normal application without seeding again. It does not repair or regenerate existing PDFs or signatures.
- `task reset` refuses ordinary, adopted, legacy, or ambiguous environments. For a completed fresh bootstrap it displays the owner and exact resources, then requires the owner UUID before removing only those verified resources and running `task setup:fresh` again. When persistent volumes of a completed bootstrap were removed outside these tasks, Compose commands name the missing volumes and refuse to start; `task reset` verifies the saved container engine, lists them, removes what remains after the same confirmation and creates a new environment. An owned volume that is not in the marker still makes it refuse. It never runs `docker compose down -v`.
- `task clean` applies the same checks and owner confirmation as `task reset` and removes the same resources, then also removes the project's Odoo image, `.local/demo-bootstrap.json` and the saved selection lines of `tools/infrastructure/.env`, without creating a new environment. The worktree is left unselected, so the next `task setup:fresh:select` picks new ports, keeping the defaults when they are free.
- `task upgrade` keeps normal module upgrade behavior. Installing `sol_demo` through `task upgrade MODULES=...` is refused unless it is already installed; use `task setup:fresh` for a fresh local demo database so PDF assets are available while demo records are created.
- `task up`, `task stop`, `task restart`, `task logs` and follow-on upgrades resolve the same saved project, image, volume and port configuration after a completed bootstrap. Editing saved values causes the wrapper to refuse startup rather than falling back to another checkout's resources.
- `task logs` streams Odoo's current container log with color on recognized severity labels when the terminal supports it. `NO_COLOR=1` or `FORCE_COLOR=0` makes it plain; `FORCE_COLOR=1` requests color even when redirected.
- Normal local Odoo startup uses the installed view XML. To hot reload XML files while developing, run `ODOO_DEV=xml task up` explicitly. In PowerShell, set `$env:ODOO_DEV = 'xml'` and run `task up`. This recreates the Odoo container with Odoo's XML developer mode and can produce QWeb warnings for upstream `technical_usage` metadata. Remove `ODOO_DEV` and run `task up` to return to normal view loading; `task restart` alone does not change a container's environment. Fresh demo bootstrap never forwards `ODOO_DEV` to its private installation or seeding containers.
- PayOS credentials are optional for the normal local Compose stack. `task doppler` authenticates but does not export secrets to later Task commands. To opt in, run `doppler run --project medilab --config dev -- task up` from a trusted local environment with all three `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY` configured in that Doppler config. Compose forwards each variable only when present in the caller's environment. The fresh local demo bootstrap does not forward these credentials, even when its caller has them. Review the PayOS provider and queued jobs before recreating an existing Odoo container with credentials; a container restart alone does not change its environment.
- After failure or interruption, ordinary `task setup` is blocked. Inspect the project and owner shown by `task setup:fresh:recover`; confirm the owner UUID only when every listed resource belongs to that failed fresh attempt. Recovery removes only those owner-labeled containers, volumes and network. Run `task setup:fresh` afterward to create a new environment. If ownership cannot be proven, recovery refuses to remove resources.
- Installing `sol_demo` normally outside this explicit local bootstrap mode keeps its existing post-init behavior.
- The fresh local flow does not convert an existing chart. It refuses any bootstrap database with accounting moves before loading the Vietnamese chart. Odoo 20's Vietnamese localization does not supply a domestic fiscal position; invoices without a fiscal position remain valid when their taxes match the company's Vietnamese fiscal country.

To try a second fresh environment from the same checkout, choose a new project name that has never owned Compose resources:

```bash
task setup:fresh:switch PROJECT=medilab-bootstrap-mytest
task setup:fresh
python tools/scripts/local_compose.py ps
docker volume ls --filter label=com.docker.compose.project=medilab-bootstrap-mytest
task logs
task restart
task stop
```

The selection command prints the chosen Odoo port. `task stop` removes containers and the network while keeping the four owner-labeled persistent volumes. `task up` starts the same saved environment again. Keep `.local/demo-bootstrap.json` and `tools/infrastructure/.env` together; if either saved identity is edited or lost, normal Compose operations refuse ownership rather than adopting another project's resources.

## Related documents

- [Settings](../specs/settings.md)
- [Secrets](../infrastructure/secrets.md)
- [Module boundaries](../business/module-boundaries.md)

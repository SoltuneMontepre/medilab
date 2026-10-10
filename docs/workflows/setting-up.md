# Setting up a laboratory

How a laboratory installs and configures MediLab the standard Odoo way, step by step, and what to check after each step. The steps need Odoo experience, not a developer.

## Steps

1. **Install Odoo 20 and the modules.** Add `src/core/modules` to the addons path of an Odoo 20 server, or run the published image, which has them. Create the database without demo data.
   Check: Odoo opens and the Apps menu is available.
2. **Update the app list and install Laboratory.** Apps → Update Apps List, then install **Medilab - Laboratory**. Install **Medilab - E-commerce** and **Medilab - Inventory** only if the laboratory uses them; each needs Laboratory only.
   Check: the app drawer shows Master Data, People and System; with E-commerce, the E-commerce app too.
3. **Company.** Settings → Companies: the laboratory's name, address, tax ID, logo and bank account. They print on every document.
   Check: the login page and the documents show the laboratory's name and logo.
4. **Languages.** Settings → Languages: activate Vietnamese (`vi_VN`) when staff or customers use it; each user picks their language in their preferences.
   Check: a user who switches to Vietnamese sees translated menus.
5. **MediLab settings.** System → Settings opens the MediLab tab, one block per installed module.
   - Laboratory: **Code formats** lists the sequences of every code and document number; change the prefix, padding or next number as the laboratory wants. Existing codes keep their value.
   - E-commerce: the invoice due days, and PayOS (next step).
   Check: a new test parameter saved without a code gets one in the chosen format.
6. **PayOS (E-commerce).** Put the merchant's `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY` in the environment of the Odoo server; in the repository they are Doppler secrets injected by `task up` ([Secrets](../infrastructure/secrets.md)). Then in System → Settings turn **PayOS payments** on, keep on the payment methods the laboratory offers and set how many hours a payment link stays payable. Register `<address of the server>/medilab/payos/webhook` as the webhook in the PayOS dashboard. When environments share one PayOS merchant, set the next number of the payment link order code apart in Code formats.
   Check: the block shows no warning about missing credentials, and **Create payment link** on a posted invoice opens a pending link with a checkout page. System → Jobs lists "PayOS queued calls" and "PayOS status check" with a next run.
7. **Departments, people and roles.** People → Departments, then Roles (a role is a set of permissions), then People with their department, login and roles. The administrator role ships with the module and holds every permission.
   Check: a person signs in with their login and sees only the menus of their roles.
8. **Master data.** Master Data: units, sample types, parameter groups, test parameters with their ways of testing, regulations, machines, chemicals, subcontractors.
   Check: a parameter shows at least one way of testing with a unit and a department or subcontractor.
9. **Demo data (optional).** On a trial installation only, install **Medilab - Testing Data** (`task upgrade MODULES=demo` from the repository): realistic records and a `demo.<role>` user per role, whose password is `MEDILAB_DEMO_PASSWORD` at install, or the login when it is unset.
   Check: signing in as `demo.tester` shows the tester's screens.

A fresh installation works with the defaults: every setting has one, and only what the laboratory wants to change needs a visit to the settings screens.

## Related documents

- [Settings](../specs/settings.md)
- [PayOS](../specs/payos.md)
- [Shared technical features](../functional/shared.md): SH-01, SH-02, SH-03
- [Secrets](../infrastructure/secrets.md)
- [Resolving an issue](resolving-issue.md)

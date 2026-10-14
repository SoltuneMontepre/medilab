# Setting up

Install and configure a laboratory. Each step says what to check before the next.

## Steps

1. **Odoo.** Install Odoo 20 Community. Add the MediLab modules and update the app list.
2. **Laboratory.** Install Laboratory on its own. Check: the catalog, people and Tasks menus open, and signing in as the administrator reaches them.
3. **Company.** Set the company name, address, logo and time zone to Asia/Ho_Chi_Minh. The time zone is the one sample-test due dates use.
4. **Languages.** Install Vietnamese and set it on the users who work in it.
5. **E-commerce and Inventory.** Install either or both on top of Laboratory. Each runs without the other. Set the company country to Vietnam and load the Vietnamese accounting chart before issuing invoices; E-commerce does not issue them through an e-invoice provider.
6. **Settings.** Settings, under the Laboratory app's Configuration menu or in Odoo's Settings app, opens one block per installed MediLab module. Laboratory holds the safety margin and Code formats. A missing value falls back to its default.
7. **Code formats.** Code formats lists the `medilab.*` sequences. Change a prefix or padding there; codes already given keep their value.
8. **Demo data.** Install the demo module only on a database used for trying the system. It is not part of a laboratory's installation.

A fresh installation works with the defaults: every setting has one, and only what the laboratory wants to change needs a visit to the settings screen.

## Related documents

- [Settings](../specs/settings.md)
- [Secrets](../infrastructure/secrets.md)
- [Module boundaries](../business/module-boundaries.md)

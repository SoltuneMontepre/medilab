# Translation and menu conventions

## Languages

- Installing or upgrading `sol_laboratory` installs English and Vietnamese with Odoo's languages, which loads Odoo's own Vietnamese translations and each module's `i18n/vi.po`. Another language is installed from Odoo's settings, with no code change.
- Every string a user sees is written in English in the source and translated to Vietnamese in the module's `i18n/vi.po`. The source language is never Vietnamese.
- Vietnamese terms for domain concepts come from the [glossaries](../glossaries.md). Do not translate a glossary term differently in a module.
- A change to a user-facing string updates `i18n/vi.po` in the same change. Regenerate the template with `odoo i18n export -d <db> -o <module>/i18n/<module>.pot <module>` inside the Odoo container, then fill in the Vietnamese `msgstr`.
- `TestTranslations` in `sol_laboratory` lists every user-facing string of an installed `sol_` module that its `i18n/vi.po` does not translate, and fails. It runs with `task test:core`, so a missing translation fails CI.
- Check a translation by upgrading the module and switching your language to Vietnamese in your preferences.
- E-mails and reports are rendered in the recipient's language, as Odoo does: a template without a language uses its main recipient's contact language. A report sets `t-lang` to the customer's contact language.

## Menus

- A MediLab module adds its menus to the apps [Module boundaries](../business/module-boundaries.md#menus) lists and keeps the Odoo apps' own menus. Master data goes in the Master Data app, and analysis under the Reporting menu of the app it is about. An area no Odoo app holds, such as the laboratory's testing work, is its own app in the app launcher.
- An app is added only when it has at least one working menu item; Odoo hides root menus that have no action.
- Menu names reuse the glossary names. A new app or item with a domain term adds that term to the glossaries.

## Related documents

- [Glossaries](../glossaries.md)

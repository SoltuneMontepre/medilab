# Translation and menu conventions

## Languages

- Installing or upgrading `sol_laboratory` installs English and Vietnamese with Odoo's languages, which loads Odoo's own Vietnamese translations and each module's `i18n/vi.po`. Another language is installed from Odoo's settings, with no code change.
- Every string a user sees is written in English in the source and translated to Vietnamese in the module's `i18n/vi.po`. The source language is never Vietnamese.
- Vietnamese terms for domain concepts come from the [glossaries](../glossaries.md). Do not translate a glossary term differently in a module.
- A change to a user-facing string updates `i18n/vi.po` in the same change. Regenerate the template with `odoo i18n export -d <db> -o <module>/i18n/<module>.pot <module>` inside the Odoo container, then fill in the Vietnamese `msgstr`. Odoo reads `i18n/vi.po` merged with the template: the template's `#:` references replace those of `vi.po`, an entry the template lacks is dropped, and a record or view translation applies only to the references listed. A string reused by a new field, selection value or view therefore needs its new reference in the template as well as in `vi.po`.
- `TestTranslations` in `sol_laboratory` reads the `i18n/vi.po` of each installed `sol_` module merged with its template, as Odoo does, lists every user-facing string that has no Vietnamese at one of its places, and fails. A place is the field, selection value, record or view the string is on; for a string in Python or JavaScript code it is `odoo-python` or `odoo-javascript`, the mark the template's entry needs next to a `code:` reference. It runs with `task test:core`, so a missing translation or reference fails CI.
- A view, record or JavaScript string of an Odoo module that Odoo does not translate to Vietnamese is translated in `i18n_extra/vi.po` of the `sol_` module that depends on that Odoo module: `sol_laboratory` for `web`, `mail`, `portal` and `auth_signup`, `sol_commerce` for `account` and `payment`. Odoo loads it with the module; each entry names the Odoo view, record or JavaScript file it translates. A JavaScript entry is marked `#. odoo-javascript`: the web client uses it when the string's own module leaves it untranslated. Strings in Odoo's Python take translations only from their own module, so they cannot be translated this way.
- Check a translation by upgrading the module and switching your language to Vietnamese in your preferences.
- E-mails and reports are rendered in the recipient's language, as Odoo does: a template without a language uses its main recipient's contact language. A report sets `t-lang` to the customer's contact language.

## Menus

- A MediLab module adds its menus to the apps [Module boundaries](../business/module-boundaries.md#menus) lists and keeps the Odoo apps' own menus. Master data goes in the Master Data app, and analysis under the Reporting menu of the app it is about and again in the Reports app, under the group of its area. An area no Odoo app holds, such as the laboratory's testing work, is its own app in the app launcher.
- An app is added only when it has at least one working menu item; Odoo hides root menus that have no action.
- Menu names reuse the glossary names. A new app or item with a domain term adds that term to the glossaries.

## Related documents

- [Glossaries](../glossaries.md)

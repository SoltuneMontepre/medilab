# Translation and menu conventions

## Languages

- Every string a user sees is written in English in the source and translated to Vietnamese in the module's `i18n/vi.po`. The source language is never Vietnamese.
- Vietnamese terms for domain concepts come from the [glossaries](../glossaries.md). Do not translate a glossary term differently in a module.
- A change to a user-facing string updates `i18n/vi.po` in the same change. Regenerate the template with `odoo i18n export -d <db> -o <module>/i18n/<module>.pot <module>` inside the Odoo container, then fill in the Vietnamese `msgstr`.
- Check a translation by loading `vi_VN` (`odoo i18n loadlang -d <db> -l vi_VN`) and upgrading the module.

## Menus

- Each functional area is its own app on the home screen. A module can own several apps.
- An app is added only when it has at least one working menu item; Odoo hides root menus that have no action.
- Menu names reuse the glossary names. A new app or item with a domain term adds that term to the glossaries.

## Related documents

- [Glossaries](../glossaries.md)

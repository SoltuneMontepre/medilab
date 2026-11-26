# Styling conventions

How screens look, so the same meaning always has the same look.

## Colors carry meaning

Buttons, status badges and list rows take their color from what they mean. The colors are the theme tokens in `sol_theme/static/src/scss/tokens.scss`, which `odoo_variables.scss` maps onto Odoo's theme colors, so views use the Odoo classes and stylesheets use the tokens; neither repeats a color code.

| Meaning                                   | Color  | Token                     | Buttons                                              | Statuses and rows                                                  |
| ----------------------------------------- | ------ | ------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------ |
| Destroys, stops or refuses                | Red    | `$ml-danger`              | `btn-danger`: cancel, delete, reject, release a lock | `decoration-danger`: cancelled, rejected, failed, overdue          |
| Accepts or finishes                       | Green  | `$ml-success`             | `btn-success`: accept, approve, confirm, mark done   | `decoration-success`: done, approved, signed, sent                 |
| Waits for someone or something            | Yellow | `$ml-warning`             | none                                                 | `decoration-warning`: open in a queue, pending, waiting to sign    |
| Moves the work forward                    | Blue   | `$ml-primary`, `$ml-accent` | `btn-primary`: claim, start, send for approval     | `decoration-info`: assigned, in progress, scheduled                |
| Anything else                             | Grey   | `$ml-text-muted`          | `btn-secondary`                                      | `decoration-muted`: archived, finished rows in a list of open work |

- The button that confirms a dialog is green, and the button that closes it without saving is grey.
- A destructive action never takes the green or blue of an accepting one, even when it is the main action of the screen.
- A color is never the only sign: the label or the status text says the same thing.
- An action looks like a button, with its fill and border, in lists too; a link only opens another record or page.
- Controls take `$ml-border-control` for their outline, which meets 3:1 on white; `$ml-border` is only for dividers and cards.
- Sizes, letter spacing, line heights, focus ring and icons come from the `$ml-font-size-*`, `$ml-letter-spacing-*`, `$ml-line-height-*`, `$ml-focus-ring` and `$ml-icon-*` tokens.
- A flag that only one line of a list can have is a checkbox that clears the others when ticked, not a toggle.
- `sol_theme` overrides Odoo and Bootstrap styles that are set with `!important` or with more specific selectors, so its stylesheets use `!important` where an override needs it. SonarQube ignores its rule S9423 (`!important`) for `sol_theme/static/src/scss/`, set in `sonar-project.properties`.

## Customer portal

The customer portal, the catalog, the cart and the pages of **My account**, looks like the back office, so customers and staff see one product.

- **Same variables.** The portal's stylesheet takes the back office's Bootstrap variables: `sol_theme` adds Odoo's `web/static/src/scss/bootstrap_overridden.scss` to `web._assets_frontend_helpers`, so the colours, text, links, borders, radii and fonts that `odoo_variables.scss` sets reach both. `frontend_variables.scss` holds only what the portal sets differently: its page is white, because it has no sheets, its tables keep Bootstrap's spacing so their columns fit on a phone, and its dividers and controls take the tokens of the list above.
- **Header.** The header is the back office's navbar: `bg-primary`, its links in `$ml-text-on-primary`, and the current section underlined in `$ml-accent-light`.
- **Components.** Buttons take the colours of `$o-btns-bs-override`, as in the back office, and the back office's `buttons.scss` and `modals.scss` style the portal's buttons and dialogs too. A table's header row is `$ml-bg`, as a list's. `portal.scss` holds only what a variable cannot set.
- **No other palette.** Odoo colours the portal's links and primary buttons with the company's e-mail colours; `sol_theme` removes them, so the theme's colours apply.

## Medilab Mobile

[Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md) looks like the web, so a person sees one product on both.

- **Tokens.** `src/applications/medilab-mobile/src/theme.ts` holds the tokens of `tokens.scss` under the same names in camel case, such as `$ml-primary-light` as `colors.primaryLight`. A token changed on the web is changed there in the same change. Screens take colours, sizes and radii from `theme.ts` and never repeat a colour code.
- **Colors by meaning.** The table above applies to the phone: a button's `tone` is `primary`, `success`, `danger` or `secondary`, and a status badge's `tone` is `info`, `success`, `warning`, `danger` or `muted`, for the same meanings as the web's `btn-*` and `decoration-*`.
- **Icons.** The phone uses Material Design Icons, the set the web names `mdi:<name>`, through `MaterialCommunityIcons` of `@expo/vector-icons`, so an action keeps the same icon on the web and the phone.
- **Light only.** The app has the web's light theme and no dark theme.
- **Brand.** The app icon, the splash screen and the sign-in screen show the MediLab mark of `sol_theme/static/src/img/medilab.svg`. The splash screen and the navbar take `$ml-primary`.

## Medilab Sync

[Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md) shows the web's logo, so a person recognises it as MediLab on the desktop.

- **Brand.** The installer, the taskbar and tray, the window and the Windows Store tiles show the MediLab mark of `sol_theme/static/src/img/medilab.svg`. `public/app-icon.svg` and `src-tauri/icons/logo.svg` are copies of it, and every icon in `src-tauri/icons/` is generated from it with `bunx tauri icon`; a test fails when the copies differ from the web's mark. A change to the mark regenerates them in the same change.

## Related documents

- [UX and UI](ux-ui.md)
- [Translation and menus](translation.md)
- [Module structure](module_structure.md)

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

## Related documents

- [UX and UI](ux-ui.md)
- [Translation and menus](translation.md)
- [Module structure](module_structure.md)

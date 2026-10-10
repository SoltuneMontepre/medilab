# Styling conventions

How screens look, so the same meaning always has the same look.

## Colors carry meaning

Buttons, status badges and list rows take their color from what they mean. The colors are the theme tokens in `laboratory/static/src/theme/scss/tokens.scss`, which `odoo_variables.scss` maps onto Odoo's theme colors, so views use the Odoo classes and stylesheets use the tokens; neither repeats a color code.

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

## Related documents

- [Translation and menus](translation.md)
- [Module structure](module_structure.md)

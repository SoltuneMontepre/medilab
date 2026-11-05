# UX and UI conventions

Rules every screen follows, so the interface reads as one product. Colors by meaning are in [Styling](styling.md); the values are the theme tokens in `sol_theme/static/src/scss/tokens.scss`.

## Visual hierarchy

- **Contrast.** Icons and controls that act stay legible on every background: give them a subtle container or outline instead of a bare glyph.
- **One grid.** Fields, labels, buttons and sections align to the same grid; the same kind of element sits in the same place on every screen.
- **Soft dividers.** Separate sections with light strokes (`$ml-border`) and spacing, not heavy lines or boxes. Use `$ml-border-strong` only where a control needs an outline.
- **Natural palette.** Soft, harmonious colors support the content. Strong color is kept for meaning, as in [Styling](styling.md).

## Typography

- **One font family.** Structure comes from size, weight and line height, never from a second family.
- **Spacing.** Headings take slightly wider letter spacing; body text takes enough line height to scan comfortably.

## Content

- **Uniform imagery.** Avatars, logos and photos share one size, shape and framing per place they appear.
- **Metadata next to the subject.** Status, assignee, dates and other facts that tell the user whether to act sit beside the record's name, in lists, cards and form headers alike.
- **No redundant text.** Drop a label, hint or title when the field name or its context already says it.

## User flow

- **Icons on portal actions.** In the customer portal every action button and button-styled link shows an Odoo icon (`<i class="oi" data-icon="…">`) before its label, and the same action keeps the same icon and look on every page. A button that only closes a dialog and the cart's quantity steppers have none.
- **Action beside its content.** A button sits next to the data it changes: row actions on the row, section actions in the section header.
- **Show the outcome first.** Totals, counts and the effect of an action update as the user edits, and a confirmation dialog states what will change before it is confirmed.
- **Sticky controls.** The status bar, the main action buttons and a list's column headers stay visible while the page scrolls.
- **Resizable chatter.** On a wide window, dragging the bar between a form and its chatter resizes the chatter, and the bar collapses the chatter to give the form the full width. The width and whether it is collapsed are kept in the browser's local storage only.
- **Predefined options.** Offer the common choices as one-click filters, groupings, default values or quick picks, and keep a custom option for anything else.

## Checking a screen

A screen that adds or changes a view is checked in the browser against these rules, in English and Vietnamese, on a narrow and a wide window, before the pull request is opened.

## Related documents

- [Styling](styling.md)
- [Frontend](frontend.md)
- [Translation and menus](translation.md)

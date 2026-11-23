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

## Medilab Mobile

The phone app follows the rules above and the web's patterns, adapted to a phone held in one hand.

- **Navbar.** Every screen has the web's navbar on top in `$ml-primary`: the screen's title, its own actions as icons, and the notifications, marked while one is unread. A screen opened from another has a back arrow, and its title is the record's code; it never shows a full breadcrumb.
- **Tabs.** The places a person goes to most are tabs at the bottom. A record opened from a tab hides the tab bar and returns to that tab.
- **Menu.** The other apps are tiles of the Menu tab, as the web's app drawer shows them, above the person's account.
- **Lists.** A list shows each record as a card of the web's kanban: its name with its status badge, then the facts that tell whether to act, each beside its icon; an overdue deadline is red. Filters are pills above the list. Pulling the list down reads it again, the next page is read when the person scrolls to the end, and an empty list says so under the icon of what it lists.
- **Records.** A record's screen opens with its name, status badge and key facts, then white sheets of label and value rows, as the web's form sheet. Its actions stay in a bar at the bottom: at most two buttons, the main one first, and the others behind a "more" button. A row that opens another record or page is a link row with a chevron, never a button.
- **Confirmations.** A step that confirms an action, such as signing or rejecting, rises as a bottom sheet that names what will change, with the confirming button and a grey cancel.
- **Forms.** A label sits above its field. Common values are pills that fill the field in one tap, and the field still takes any other value.
- **Touch and text.** Every control is at least 48 points high or wide, an icon-only button has an accessibility label, and text follows the phone's font size.
- **Tablets.** A tablet shows the phone's layout, no wider than 720 points and centred.

## Checking a screen

A screen that adds or changes a view is checked in the browser against these rules, in English and Vietnamese, on a narrow and a wide window, before the pull request is opened. A screen of Medilab Mobile is checked the same way on an Android emulator, on a phone and a tablet.

## Related documents

- [Styling](styling.md)
- [Frontend](frontend.md)
- [Translation and menus](translation.md)

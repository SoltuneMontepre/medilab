# Activity diagrams

The system activity map and one activity diagram per business flow of [Business flows](../../functional/business-flows.md): the core flows WF-01 to WF-06, which carry a test request from order to report, and the supporting flows SF-01 to SF-11. The [website](https://medilab-activity-diagrams.vercel.app) shows them: the map links to the page of each flow, and each page names the flows it comes from and leads to.

![System activity map](<final/System activity map.svg>)

## Files

- [final](final): the diagrams, named with their ID and title. Each `.drawio` file is the source; the build writes the `.svg` of each page next to it, and a `.png` of each page for a core flow.
  - `System activity map`: the flows, the events that start a flow on its own, and the hand-overs between flows.
  - `Core flows`: each WF has a Workflow page and a Demo scenarios page, whose bands each name the path of business-flows.md they show.
  - `Supporting flows`: one page per SF.
- [activity-diagrams-final.pdf](activity-diagrams-final.pdf): the map and the Workflow page of each flow, with a bookmark for each.
- [activity-diagrams-final.zip](activity-diagrams-final.zip): the `final` folder.
- [site](site): `build.py` builds the website into `site/public`, then the pictures, the zip and the PDF; `static` holds its stylesheet and script.

## Reading a diagram

- A lane is the actor who acts; a role in square brackets names who in that lane may act, such as `[folder owner]` in SF-11.
- A solid box is an actor's activity, a dashed box a system activity and a diamond a decision; in the core flows, a blue dashed box with ✉ is a notification.
- The black dot starts the flow, the ringed dot ends it with an outcome, and the crossed circle hands the work to another flow.

## Changing a diagram

Edit its `.drawio` file in `final` with draw.io desktop, keeping its ID and title in the file name, then build and deploy from `site`:

```bash
uv run --with pypdf python build.py
vercel deploy --prod --yes --project medilab-activity-diagrams
```

The build needs draw.io desktop for the exports. Titles come from the `##` headings of business-flows.md, so a renamed flow is renamed in the menus and pages by the next build.

## Related documents

- [Business flows](../../functional/business-flows.md)
- [Reports](../readme.md)

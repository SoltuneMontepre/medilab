# Merge brief: Tuyen's flow diagrams

One session merges one core flow, WF-0x. The owner decides every difference; you prepare it, show it and apply it. Talk to the owner in Vietnamese.

## Files

- **The file you edit:** `docs/reports/activity-diagram/flows-work-of-tuyen/[Flow] WF-0x <name>.drawio`, Tuyen's diagram. It is the main file: edit it directly. It has two pages, Workflow and Demo scenarios.
- **The owner's version, for comparison only:** `docs/reports/activity-diagram/flows/wf-0x.drawio`, generated from business-flows.md. Do not edit it.
- **The requirements:** the `## WF-0x` section of `docs/functional/business-flows.md` and the feature documents it links. Read them; do not edit them.
- **Your working folder:** `docs/reports/activity-diagram/flows-work-of-tuyen/_review/wf-0x/` for the mapping, the snapshots and the diff pages.

Write nothing outside `flows-work-of-tuyen/`. Do not commit, do not create a worktree and do not touch another flow's files.

## Rules

1. **Business-flows.md decides the content.** Where Tuyen's diagram contradicts it, recommend the document's version; the owner may decide otherwise for that item. Some of Tuyen's work follows older requirements, such as the approval after the order is confirmed in WF-01, which PR 243 removed.
2. **Record every accepted difference from the document** in `_review/wf-0x-doc-changes.md`: what the diagram now shows, which part of business-flows.md it concerns, and the new text. The documents are updated later from these notes.
3. **Notation:** initial node (●), activity final (◉) for an end with an outcome, flow final (⊗) for a path that only hands the work over; the legend shows the symbols in use. Keep Tuyen's lane order, colours, notification shape (✉) and title band. Lanes are real actors; ask the owner where a new lane goes.
4. **A flow ID never stands alone.** Write "→ WF-04 Result entry and approval", never "→ WF-04". Titles come from the headings of business-flows.md.
5. **No crossings.** After every change run `check.py`; it must report 0 crossings on both pages.
6. **Keep cell ids.** Change a cell in place; give a new cell a new id. Copy the style of a similar cell of the same file for new cells.

## Showing a diff

The owner reads the diffs in Claude Desktop and does not want to download anything. Show the **PNG pictures** that `flow_diff.py` prints after `picture:`, with SendUserFile and `display: "render"`; they appear inline:

- after `compare`: `_review/wf-0x/compare/compare.png`
- after `change`: `_review/wf-0x/step-NN/page1-diff.png` and `page2-diff.png`, one per page that changed

Each picture has the list of changes on top and the two coloured drawings side by side. Do not send `diff.html`; it stays in the folder for the details.

## How to work

Run the tools from `docs/reports/activity-diagram/flows-work-of-tuyen`:

```bash
python _review/convert_icons.py "<file>.drawio"
python _review/flow_diff.py change <before>.drawio "<file>.drawio" _review/wf-0x/step-NN
python _review/flow_diff.py compare "<file>.drawio" ../flows/wf-0x.drawio _review/wf-0x/mapping.json _review/wf-0x/compare
python _review/check.py "<file>.drawio"
```

1. **Compare.** Pair the cells of Tuyen's Workflow page with the owner's version by meaning in `_review/wf-0x/mapping.json`: `{"pairs": [{"tuyen": "<id>", "mine": "<id>", "same": true|false, "note": "<what differs, in Vietnamese>"}]}`. Run `compare` and show `compare.png` (see Showing a diff).
2. **Change 1: notation.** Copy the file to `_review/wf-0x/step-01-before.drawio`, run `convert_icons.py` on the file, run `check.py`, run `change` into `_review/wf-0x/step-01` and show its pictures.
3. **Differences, one at a time.** For each difference of the comparison, state it, give the options (keep Tuyen's, take the owner's, combine, drop) with your recommendation from business-flows.md, and wait. Apply the answer as the next step: snapshot `step-NN-before.drawio`, edit, `check.py`, `change`, show its pictures. One decision, one step.
4. **Demo scenarios.** Then review the Demo scenarios page the same way. Each scenario names the path of business-flows.md it shows, such as "DS-01b ↔ WF-01-E1"; a scenario of a removed behaviour follows rule 1.
5. **Finish.** Export the two pictures again over Tuyen's PNG files, with the same names:

   ```bash
   drawio -x -f png -p 1 -o "<name> - Workflow.png" "<file>.drawio"
   drawio -x -f png -p 2 -o "<name> - Demo scenarios.png" "<file>.drawio"
   ```

   Then tell the owner what was decided and what `wf-0x-doc-changes.md` holds.

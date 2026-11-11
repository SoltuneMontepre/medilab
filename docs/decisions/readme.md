# Decisions

Architecture decisions the owner approved: what was decided, why, and the requirements that come with it. A decision record does not change once approved; a later decision that replaces it is a new record, and the old one links to it.

## Writing a decision record

- One record per decision, or per set of decisions approved together, named after its topic: `<topic>.md`.
- A record gives the date of the approval, the context, each decision with its rationale and the options not chosen, its requirements with an ID and a priority, and what it does not decide. It ends with **Related documents**.
- Specs and issues carry the requirements: a spec describes the design that meets them, and an issue lists the ones it builds as acceptance criteria, by ID.

## Decisions

- [Laboratory files architecture](laboratory-files-architecture.md): the laboratory files API as Odoo HTTP controllers under `/medilab/api/v1`, a private content-addressed bucket of their own, and ONLYOFFICE Community Edition for online editing

## Related documents

- [Documentation conventions](../conventions/documentation.md)
- [Specs](../specs/readme.md)

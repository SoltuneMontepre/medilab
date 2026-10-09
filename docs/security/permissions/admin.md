# Administrator

The administrator maintains master data, people, roles, approval chains, prices and settings. All permissions cover every record. The administrator signs nothing unless they also hold a role that signs.

## Laboratory

| Document type                                   | Read | Create | Edit | Archive | Delete | Sign |
| ----------------------------------------------- | ---- | ------ | ---- | ------- | ------ | ---- |
| Test parameter, parameter and method pair       | ✓    | ✓      | ✓    | ✓       |        |      |
| Parameter group, sample type                    | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Testing field, testing method                   | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Measurement unit, unit category                 | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Regulation and its limits                       | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Quality registration                            | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Machine                                         | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Machine service record                          | ✓    | ✓      | ✓    | ✓       |        |      |
| Chemical                                        | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Subcontractor                                   | ✓    | ✓      | ✓    | ✓       |        |      |
| Person                                          | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Department                                      | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Role and its permissions                        | ✓    | ✓      | ✓    |         | ✓      |      |
| Approval chain and its levels                   | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Task type                                       | ✓    | ✓      | ✓    | ✓       |        |      |
| Customer                                        | ✓    |        |      |         |        |      |

## E-commerce

| Document type                  | Read | Create | Edit | Archive | Delete | Sign |
| ------------------------------ | ---- | ------ | ---- | ------- | ------ | ---- |
| Parameter price                | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Tax and its rates              | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Subcontract cost               | ✓    | ✓      | ✓    | ✓       | ✓      |      |
| Service package                | ✓    | ✓      | ✓    | ✓       | ✓      |      |

## System

- Changes settings, including the urgency threshold, the due date safety margin and the reminder lead time, scheduled job schedules and the Brevo and Viettel Sign configuration; every change is audited.
- Searches the audit trail, but cannot edit or remove an entry.
- Releases an editing lock that is stuck; this is audited.
- Runs a scheduled job by hand and retries a failed one.
- Cannot change a signed document.

## Related documents

- [Security](../readme.md)
- [Laboratory administrator](../../functional/laboratory_module/features/admin.md)
- [E-commerce administrator](../../functional/ecommerce_module/features/admin.md)
- [Shared technical features](../../functional/shared.md)

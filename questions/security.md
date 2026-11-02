# Security questions

- **Operational documents.** Which roles read, create, edit and sign test requests, samples, sample tests and results, and does the administrator have any of these permissions?
- **Role permissions.** Only the administrator's permissions are documented. The demo seeds the other roles with what its scenarios need: the head of department reads people of their own department, the lab head reads people and departments, the tester holds one direct permission. Which permissions is each role set up with? (blocks US-AD15)
- **Archived people.** Archiving a person archives their Odoo user, so they can no longer sign in. Is that wanted, or should an archived person keep signing in? (blocks US-AD13)
- **Passwords.** Only Odoo administrators set a person's password, from the user form. May someone allowed to edit people set it too? (blocks US-AD13)
- **Role terms.** The requirements give no Vietnamese names for the roles, so the glossary proposes them. Are they right? Lab head (Trưởng Phòng Thí Nghiệm) and head of department (Trưởng Phòng) read very close. (blocks US-AD15)
- **Subcontractor contact people.** The subcontractor permissions create and change the subcontractor's company contact, but creating a new contact person from the subcontractor form still needs Odoo's contact rights, which only administrators hold. Should the subcontractor permissions let people create its contact people too? (blocks US-AD12)
- **Records without a department.** A permission limited to the person's department does not show records that have no department. Should such records be visible to everyone with that permission instead? (blocks US-AD15)
- **Sonar dispositions.** The Accountable Risk Owner remains TBD for designation by the MediLab project/repository owner; the Authorized Security Approver remains TBD for designation by security governance. Who will formally hold these roles and individually verify the three current proposed False Positives (RFC 6455 public nonce, fixed Unix socket, TLS-wrapped listener) in the PR #292 owner request? Six original HTTP findings are automatically FIXED through TLS, with no risk acceptance or administrative classification. Git authorship and engineering authorization grant no security authority. (blocks #171/#203/#230/#206 security disposition and PR #292 merge)

## Related documents

- [Administrator permissions](../docs/security/permissions/admin.md)
- [Permissions](../docs/specs/permissions.md)

# Laboratory files

Stories: US-T23, US-T28, US-AD29, US-AD30

## Goal

People reach the [laboratory files](../functional/laboratory_module/overview.md#laboratory-files) only through the folders they are members of, and only with the laboratory files permission. One check decides what a person may do with a folder, so the laboratory files API and the features built on folders refuse the same things the same way. Each computer signs in once with the person's login and gets its own key, which stops at once when the computer is revoked.

## Design

### Permissions

| Document type            | Actions                    | Scopes |
| ------------------------ | -------------------------- | ------ |
| Laboratory folder        | read, create, edit         | all    |
| Laboratory folder member | read, create, delete       | all    |
| Laboratory sync rule     | read, create, edit, delete | all    |
| Laboratory device        | read, edit                 | all    |

- **The create permission on laboratory folders, `laboratory_folder.create.all`, is the laboratory files permission.** Its holders sign computers in and create folders they own. Its group also carries accesses of its own: its holders read the folders they are members of, the members and sync rules of those folders, and their own computers. They change them only through the laboratory files API, which checks them and then writes with full rights.
- Folder administration is `laboratory_folder.edit.all`. With the read permissions of every folder, member, sync rule and computer, and the other permissions above, administrators see and change them all in the back office.
- Folders have no archive or delete action: archiving a folder is editing it, and folders are never deleted. Members change their role only with the folder's owner, so they have no edit action. Computers are created by signing in and revoked by editing; they are never deleted.

### What a person may do with a folder

`_check_folder_access(access)` on `medilab.laboratory.folder` refuses the user what they may not do with the folders, as a `LaboratoryFileError`: a user error carrying the code the API answers with. The API and later features call it, then act with full rights.

| Access       | Allowed when                                                                                                              | Refused with                         |
| ------------ | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| `read`       | The person holds the laboratory files permission, is a member of the folder and, for a folder of a sample, sees the sample | `permission_denied`, `not_found`     |
| `write`      | `read`, and the folder is neither archived nor turned off                                                                 | `folder_archived`, `folder_disabled` |
| `share`      | `read` and the person owns the folder, or the person administers folders                                                  | `permission_denied`                  |
| `administer` | The person administers folders                                                                                            | `permission_denied`                  |

- A person who is not a member gets `not_found`, as for a folder that does not exist, so the answer does not tell that the folder exists. So does an administrator who is not a member, except for `share`.
- `share` and `administer` are refused with `locked` while someone else holds the folder's [document lock](document-locking.md), because writing with full rights would pass over it.
- Odoo evaluates access domains with full rights, so an access cannot test whether the person sees a folder's sample. The check tests the sample in the person's own environment.

### Members

- Creating a folder adds its owner as a member with the role `owner`. A folder has one owner row, held by a partial unique index, and the owner row cannot be removed.
- Only active internal users holding the laboratory files permission are added as members. Anyone else is refused with `not_eligible` and one message that does not say why.

### Names, never paths

The API never receives or stores a path on anyone's computer:

- A folder's name and its root, the name it was created with, are one name each: no separator, drive, home folder or parent folder. Renaming changes the name; the root never changes, and it is unique for the owner.
- A sync rule's name prefix is the start of a file name without `*`, its name pattern is a file name whose only wildcard is `*`, and its extension is letters and digits, with or without its dot.

### Computers

A signed-in computer is a `medilab.laboratory.device` of its person, one per installation of Medilab Sync: the installation id the application generates once is unique for the person. Its name is one name and its platform is Linux or Windows.

| Step         | What happens                                                                                                                                                                                                                                                                  | Refused with                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Signing in   | Odoo checks the login as it does for its external API: with the password, or, for a person with two-factor authentication, with one of their API keys in its place. The password is never kept. The computer is created, or found by its installation id, and gets a new key. | `invalid_request`, `invalid_credentials`, `permission_denied`, `device_revoked` |
| A call       | Odoo verifies the key; the computer is the one holding the key's row and not revoked. Its last call is written at most once a minute, so parallel calls do not fight over its row.                                                                                          | `invalid_key`                                                   |
| Signing out  | The key is removed; the computer can sign in again and gets a new key.                                                                                                                                                                                                        |                                                                 |
| Revoking     | The key is removed and the computer is revoked for good. A person revokes their own computers, administrators any computer. The person's folder memberships and other computers stay.                                                                                         |                                                                 |

- The key is an Odoo API key of the person, in `res_users_apikeys`, with the scope `sol_laboratory.device`. Odoo keeps only its hash, and the scope makes it open the laboratory files API and nothing else, not Odoo's external API. It does not expire: it stays valid until the computer signs out or is revoked. The device keeps only the id of the key's row, and signing in again removes the old key first.
- Odoo verifies the key's hash before the call reaches the laboratory files API, and that hash is deliberately slow. So the computer of a call is found by the key's row with the person, the scope and the key's index, as Odoo finds it, with the same expiry; the hash is checked again only when two of the person's keys share an index.
- Odoo makes no foreign key to its API keys, so a key removed elsewhere, such as from the person's Odoo preferences, leaves its id on the computer, which counts as signed out. The id is cleared before the computer's next change, without an entry of the audit trail, which could not name the removed key.
- Revoking is final, also for a person's own computer: the revoked installation cannot sign in again. The computer gets back in as a new installation of Medilab Sync, which generates a new installation id and signs in as a new computer. Whether administrators can restore a revoked computer is an open question.
- Signing in, signing out and revoking are recorded in the [audit trail](audit-trail.md) as the creation and edits of the computer: signing in creates it or changes its key, signing out empties its key, and revoking empties its key and sets when it was revoked. The key's row is named, never the key.

#### Risks

- Odoo's only brake on guessing passwords is its login cooldown, which counts failures per Odoo worker. Signing in is not rate limited otherwise, so many attempts against one login can reach Odoo; the route needs a rate limit in front of Odoo, as the webhooks have.

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#laboratory-files)
- [Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md)
- [Permissions](permissions.md)
- [Document locking](document-locking.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)

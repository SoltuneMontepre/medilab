# Laboratory files

Stories: US-T23, US-T28, US-AD29, US-AD30

## Goal

People reach the [laboratory files](../functional/laboratory_module/overview.md#laboratory-files) only through the folders they are members of, and only with the laboratory files permission. One check decides what a person may do with a folder, so the laboratory files API and the features built on folders refuse the same things the same way.

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

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#laboratory-files)
- [Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md)
- [Permissions](permissions.md)
- [Document locking](document-locking.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)

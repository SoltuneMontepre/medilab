"""Member roles, sync modes and access levels of laboratory folders, and the codes of their refusals."""

OWNER_ROLE = "owner"
MEMBER_ROLE = "member"
UPLOAD_ONLY = "upload_only"
TWO_WAY = "two_way"
# What a person does with a folder: read it, write its files, share it and set its rules, or administer it.
FOLDER_READ = "read"
FOLDER_WRITE = "write"
FOLDER_SHARE = "share"
FOLDER_ADMINISTER = "administer"
# Codes of the refusals, which the laboratory files API answers with.
NOT_FOUND = "not_found"
PERMISSION_DENIED = "permission_denied"
FOLDER_DISABLED = "folder_disabled"
FOLDER_ARCHIVED = "folder_archived"
LOCKED = "locked"
NOT_ELIGIBLE = "not_eligible"

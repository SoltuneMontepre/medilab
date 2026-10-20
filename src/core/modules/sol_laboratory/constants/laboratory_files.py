"""Member roles, sync modes and access levels of laboratory folders, the key scope of the computers signed in to them,
and the codes of their refusals."""

# The scope of the Odoo API keys of signed-in computers: they open the laboratory files API and nothing else.
DEVICE_KEY_SCOPE = "sol_laboratory.device"
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
INVALID_REQUEST = "invalid_request"
INVALID_CREDENTIALS = "invalid_credentials"
INVALID_KEY = "invalid_key"
DEVICE_REVOKED = "device_revoked"

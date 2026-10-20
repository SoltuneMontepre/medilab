"""Member roles, sync modes and access levels of laboratory folders, the sources of file versions, the folder categories
whose files are locked, the key scope of the computers signed in to them, and the codes of their refusals."""

# The scope of the Odoo API keys of signed-in computers: they open the laboratory files API and nothing else.
DEVICE_KEY_SCOPE = "sol_laboratory.device"
OWNER_ROLE = "owner"
MEMBER_ROLE = "member"
UPLOAD_ONLY = "upload_only"
TWO_WAY = "two_way"
# How a version was made: synced from a computer, kept from a conflict, restored from an earlier one, or edited online.
SYNCED = "synced"
CONFLICT = "conflict"
RESTORED = "restored"
EDITED_ONLINE = "edited_online"
# The category of a sample's folder that holds the raw data of its instruments.
RAW_DATA = "raw"
# The category of a sample's folder that holds its result files.
RESULT = "result"
# The extensions of Word, Excel and PowerPoint documents.
OFFICE_EXTENSIONS = frozenset({"docx", "xlsx", "pptx"})
# Context key of the one write that moves a file's current version, made by the file itself.
MOVE_CURRENT_CONTEXT = "laboratory_file_move_current"
# What a person does with a folder: read it, write its files, share it and set its rules, or administer it.
FOLDER_READ = "read"
FOLDER_WRITE = "write"
FOLDER_SHARE = "share"
FOLDER_ADMINISTER = "administer"
# What a person does with a file: read its versions, or write a new one.
FILE_READ = "read"
FILE_WRITE = "write"
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
# The folder categories whose files are locked while someone edits them; False is a folder of no category.
LOCKABLE_CATEGORIES = frozenset({"working", "result", False})
NOT_LOCKABLE = "not_lockable"
NOT_LOCKED = "not_locked"

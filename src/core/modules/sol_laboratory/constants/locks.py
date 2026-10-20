"""Bus notification and release reasons of document locks."""

# Notification type open forms listen to on the bus; the form controller patch uses the same name.
LOCK_BUS_TYPE = "medilab.document_lock"
# Release reasons a user's own form sends.
CLIENT_RELEASE_REASONS = ("cancelled", "left")

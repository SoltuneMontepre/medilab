"""Purposes of approval chains, decisions of signatures and approval states hosts keep."""

PURPOSE_SIGNING = "signing"
PURPOSE_CHANGE_REQUEST = "change_request"

DECISION_SIGNED = "signed"
DECISION_REJECTED = "rejected"

STATE_NONE = "none"
STATE_REQUESTED = "requested"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"

# Context key that lets the system write content fields of a document that has a standing signature.
APPROVAL_SYSTEM_CONTEXT = "medilab_approval_system"

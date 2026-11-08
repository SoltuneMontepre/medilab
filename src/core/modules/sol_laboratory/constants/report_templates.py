"""States of report template versions, the data bindings of report DOCX files, the statuses of prepared PDF candidates
and the context key naming the one a signer reviewed."""

# The states of a template version: edited, used by new drafts, or kept only for the reports that used it.
DRAFT = "draft"
AVAILABLE = "available"
ARCHIVED = "archived"
# A binding is a content control whose tag is the prefix followed by the binding's name, such as medilab:customer_name.
BINDING_TAG_PREFIX = "medilab:"
# Bindings holding one line of text, which a template may place inside a paragraph.
SCALAR_BINDINGS = (
    "report_number",
    "report_date",
    "request_code",
    "customer_name",
    "customer_address",
    "received_dates",
)
# Bindings holding paragraphs and tables, which a template places as paragraphs of their own.
BLOCK_BINDINGS = ("samples", "approvers")
# Every binding an available template version must hold.
REQUIRED_BINDINGS = SCALAR_BINDINGS + BLOCK_BINDINGS
# Bindings filled when the PDF is prepared, from the reserved number and the day of preparation; a draft leaves them
# empty.
ISSUE_BINDINGS = ("report_number", "report_date")
# The statuses of a prepared PDF candidate: waiting for the lab head's review, replaced by a newer preparation or no
# longer matching its sources, or issued.
CANDIDATE_REVIEW = "review"
CANDIDATE_OBSOLETE = "obsolete"
CANDIDATE_ISSUED = "issued"
# How a candidate was made: prepared from a DOCX draft, or kept from a report issued before report templates existed.
CANDIDATE_PREPARED = "prepared"
CANDIDATE_MIGRATED = "migrated"
# Context key of the sign button of a report: the id of the prepared PDF its signer reviewed, which the signature signs.
REVIEWED_CANDIDATE_CONTEXT = "medilab_reviewed_candidate_id"

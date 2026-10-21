"""Names and values of the Onboarding module."""

# Statuses of the job items a refresh waits on.
ITEMS_OPEN = ("pending", "running")
ITEM_FAILED = "failed"

# Key of the job that refreshes the organisations, and the context key that turns an empty search into a suggestion.
ORGANISATIONS_JOB = "onboarding.organisations"
SUGGEST_CONTEXT = "onboarding_suggest"

# Key of the job that crawls the pages of a collection run, and the event that tells its starter the run ended.
CRAWL_JOB = "onboarding.crawl"
EVENT_RUN_ENDED = "onboarding_run.ended"

RUN_DRAFT = "draft"
RUN_RUNNING = "running"
RUN_DONE = "done"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"
RUN_ENDED = (RUN_DONE, RUN_FAILED, RUN_CANCELLED)

SECTOR_CODES = ("food", "cosmetics", "pharmaceuticals", "environment")

KIND_CERTIFICATE = "certificate"
KIND_TESTING_FIELD = "testing_field"
KIND_TESTING_METHOD = "testing_method"
KIND_SAMPLE_TYPE = "sample_type"
KIND_TEST_PARAMETER = "test_parameter"
KIND_PARAMETER_METHOD = "parameter_method"

# Value keys a staged record of each kind carries.
VALUE_KEYS = {
    KIND_CERTIFICATE: ("code", "issuing_body", "valid_from", "valid_until"),
    KIND_TESTING_FIELD: ("code", "name"),
    KIND_TESTING_METHOD: ("code", "name", "field_key"),
    KIND_SAMPLE_TYPE: ("name",),
    KIND_TEST_PARAMETER: ("name",),
    KIND_PARAMETER_METHOD: ("parameter_key", "method_key"),
}

# Keys a reviewer supplies when accepting; a source never provides them.
ASKED_KEYS = ("code", "field_id", "main_group_id", "unit_id", "department_id")

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 5
# Media types the fetcher accepts, with the content type of the fetched document.
CONTENT_TYPES = {"text/html": "html", "application/pdf": "pdf", "application/json": "json"}
USER_AGENT = "MediLab-Onboarding/1.0"

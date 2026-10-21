"""Names and values of the Onboarding module."""

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)

# Statuses of the job items a refresh or a run waits on, and of the items that ended.
ITEMS_OPEN = ("pending", "running")
ITEM_DONE = "done"
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

# Laboratory model a staged record of each kind matches; a way of testing matches a pair of parameter and method.
KIND_MODELS = {
    KIND_CERTIFICATE: MODEL_ACCREDITATION_CERTIFICATE,
    KIND_TESTING_FIELD: MODEL_TESTING_FIELD,
    KIND_TESTING_METHOD: MODEL_TESTING_METHOD,
    KIND_SAMPLE_TYPE: MODEL_SAMPLE_TYPE,
    KIND_TEST_PARAMETER: MODEL_TEST_PARAMETER,
    KIND_PARAMETER_METHOD: MODEL_PARAMETER_METHOD,
}

# Value keys that name the staged record of another kind a record needs, with that kind.
KIND_NEEDS = {
    KIND_TESTING_METHOD: {"field_key": KIND_TESTING_FIELD},
    KIND_PARAMETER_METHOD: {"parameter_key": KIND_TEST_PARAMETER, "method_key": KIND_TESTING_METHOD},
}

# Keys a reviewer supplies when accepting; a source never provides them.
ASKED_KEYS = ("code", "field_id", "main_group_id", "unit_id", "department_id")

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 5
# Media types the fetcher accepts, with the content type of the fetched document.
CONTENT_TYPES = {"text/html": "html", "application/pdf": "pdf", "application/json": "json"}
USER_AGENT = "MediLab-Onboarding/1.0"

STAGED_TO_REVIEW = "to_review"
STAGED_ACCEPTED = "accepted"
STAGED_REJECTED = "rejected"
STAGED_SUPERSEDED = "superseded"
# States of a key that stop an unchanged record from being staged again.
STAGED_KEPT = (STAGED_TO_REVIEW, STAGED_ACCEPTED, STAGED_REJECTED)

ACTION_CREATE = "create"
ACTION_LINK = "link"
ACTION_UPDATE = "update"

# Trigram similarity from which a name matches an existing record.
NAME_MATCH_THRESHOLD = 0.6

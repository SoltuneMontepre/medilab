"""Triggers, actions and statuses of tasks."""

MANUAL_TRIGGER = "manual"
SAMPLE_RECEIVED_TRIGGER = "sample_received"
RETENTION_DUE_TRIGGER = "retention_due"
REPORT_DRAFTED_TRIGGER = "report_drafted"
SAMPLE_COLLECTION_CODE = "sample_collection"
SAMPLE_TEST_CODE = "sample_test"
SAMPLE_RETENTION_CODE = "sample_retention"
FINAL_STATUSES = ("done", "cancelled")
# The action of the testing task a received sample creates for each of its tests.
TESTING_ACTION = "test"
# Why an administrator reviews a task that names a document: changed after it was created, created before the trail
# recorded it or with its entries archived, or naming a document or action its type does not.
LINK_CHANGED = "changed_after_creation"
LINK_UNRECORDED = "creation_not_recorded"
LINK_NOT_OF_TYPE = "not_of_its_type"

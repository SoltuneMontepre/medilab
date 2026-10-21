"""Names and values of the Onboarding module."""

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

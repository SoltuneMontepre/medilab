"""Digital signing: its jobs, the statuses of the laboratory's certificate, the context that prints without it and the
address of the verification page."""

DIGITAL_SIGNING_JOB = "digital_signing.sign"
SIGNING_CERTIFICATES_JOB = "digital_signing.certificates"

CERTIFICATE_VALID = "valid"
CERTIFICATE_EXPIRED = "expired"
CERTIFICATE_REVOKED = "revoked"

# Context key that renders a report as it is, without returning or making its digitally signed PDF.
UNSIGNED_PRINT_CONTEXT = "medilab_unsigned_print"

# The public page where anyone checks a signed PDF; every signed PDF prints it.
VERIFY_PATH = "/verify"

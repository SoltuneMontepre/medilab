"""How the audit trail masks the values of a field."""

# The value is written as *** whatever it is: tokens, secrets and credentials.
MASK_SECRET = "secret"
# The value keeps only a few characters, enough to tell values apart: personal data such as an email or a phone.
MASK_PERSONAL = "personal"

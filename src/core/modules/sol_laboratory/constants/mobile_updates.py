"""Public Medilab Mobile release discovery, separate from device authentication."""

DOCUMENT_PATH = "sol_laboratory/api/mobile-updates.openapi.yaml"
DOCUMENT_URI = "urn:medilab:mobile-updates"
RELEASE_PREFIX = "/medilab/api/v1/mobile/release"
UPDATES_PATH = "/medilab/api/v1/mobile/updates"
CATALOG_VARIABLE = "MEDILAB_MOBILE_RELEASES_FILE"
PLATFORMS = ("android", "ios")
KIND_CODE = "code"
KIND_INSTALL = "install"
ACTION_UNAVAILABLE = "unavailable"
# The key id the app's certificate is configured with, which the Expo Updates route names in expo-signature.
SIGNING_KEY_ID = "main"

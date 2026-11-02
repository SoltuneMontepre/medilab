"""Public Sync release discovery, separate from device authentication."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.http.routing_map import HTTPMethods


DOCUMENT_PATH = "sol_laboratory/api/sync-updates.openapi.yaml"
DOCUMENT_URI = "urn:medilab:sync-updates"
LEGACY_PREFIX = "/api/sync/v1"
UPDATE_PREFIX = "/medilab/api/v1/updates"
CATALOG_VARIABLE = "MEDILAB_SYNC_RELEASES_FILE"
DOWNLOAD_VARIABLE = "MEDILAB_SYNC_DOWNLOAD_URL"
LEGACY_MODE_VARIABLE = "MEDILAB_SYNC_LEGACY_UPDATER"
METHODS: list["HTTPMethods"] = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]
HEADERS = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")]

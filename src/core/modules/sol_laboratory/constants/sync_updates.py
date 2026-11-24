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

# Setting Medilab Sync up from a testing task: its installers are the latest release's, under the names cd-sync-app
# gives them, and the app takes the MediLab address from a link of its own scheme.
SETUP_DOWNLOAD_PATH = "/medilab/sync/download"
SETUP_CONNECT_PATH = "/medilab/sync/connect"
RELEASES_URL = "https://github.com/SoltuneMontepre/medilab/releases/latest"
WINDOWS_INSTALLER = "medilab-sync-windows-x64-setup.exe"
LINUX_INSTALLER = "medilab-sync-linux-amd64.deb"
CONNECT_LINK = "medilab-sync://connect"

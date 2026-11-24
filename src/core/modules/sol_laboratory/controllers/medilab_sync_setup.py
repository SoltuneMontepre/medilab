from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_USERS
from odoo.addons.sol_laboratory.constants.sync_updates import (
    CONNECT_LINK,
    LINUX_INSTALLER,
    RELEASES_URL,
    SETUP_CONNECT_PATH,
    SETUP_DOWNLOAD_PATH,
    WINDOWS_INSTALLER,
)
from odoo.addons.sol_laboratory.services.request_env import request_env


def installer_url(user_agent):
    """The latest release's installer for the browser's computer, or the release page, which lists them all, for a
    computer that has none, such as a Mac or an ARM Linux."""
    if "Windows" in user_agent:
        return f"{RELEASES_URL}/download/{WINDOWS_INSTALLER}"
    if "Linux x86_64" in user_agent and "Android" not in user_agent:
        return f"{RELEASES_URL}/download/{LINUX_INSTALLER}"
    return RELEASES_URL


class MedilabSyncSetup(http.Controller):
    """A tester downloads Medilab Sync and opens it on this MediLab from a testing task."""

    @http.route(SETUP_DOWNLOAD_PATH, type="http", auth="user", methods=["GET"], readonly=True)
    def download(self, **_parameters):
        return request.redirect(installer_url(request.httprequest.user_agent.string), local=False)

    @http.route(SETUP_CONNECT_PATH, type="http", auth="user", methods=["GET"], readonly=True)
    def connect(self, **_parameters):
        server = request_env()[MODEL_RES_USERS].get_base_url()
        return request.redirect_query(CONNECT_LINK, {"server": server}, local=False)

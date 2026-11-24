from urllib.parse import parse_qs, urlsplit

from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_CONFIG_PARAMETER
from odoo.addons.sol_laboratory.constants.sync_updates import (
    LINUX_INSTALLER,
    RELEASES_URL,
    SETUP_CONNECT_PATH,
    SETUP_DOWNLOAD_PATH,
    WINDOWS_INSTALLER,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.tests.laboratory_files_case import PASSWORD

WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36"
UBUNTU = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0"
ARM_LINUX = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36"
ANDROID = (
    "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Mobile Safari/537.36"
)
MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15"
)


@tagged("post_install", "-at_install")
class TestMedilabSyncSetup(HttpCase):
    """A tester downloads Medilab Sync and opens it on this MediLab from a testing task."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = f"base.group_user,{LABORATORY_FILES_GROUP}"
        cls.tester = new_test_user(cls.env, login="sync.setup.tester", password=PASSWORD, groups=groups)

    def location(self, path, user_agent=WINDOWS):
        response = self.url_open(path, headers={"User-Agent": user_agent}, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        return response.headers["Location"]

    def test_download_gives_each_computer_its_installer(self):
        self.authenticate(self.tester.login, PASSWORD)
        self.assertEqual(self.location(SETUP_DOWNLOAD_PATH, WINDOWS), f"{RELEASES_URL}/download/{WINDOWS_INSTALLER}")
        self.assertEqual(self.location(SETUP_DOWNLOAD_PATH, UBUNTU), f"{RELEASES_URL}/download/{LINUX_INSTALLER}")
        for other in (ARM_LINUX, ANDROID, MAC, ""):
            self.assertEqual(self.location(SETUP_DOWNLOAD_PATH, other), RELEASES_URL)

    def test_connect_link_carries_this_medilab(self):
        self.env[MODEL_IR_CONFIG_PARAMETER].set_str("web.base.url", "https://lims.example.com")
        self.authenticate(self.tester.login, PASSWORD)
        link = urlsplit(self.location(SETUP_CONNECT_PATH))
        self.assertEqual((link.scheme, link.netloc), ("medilab-sync", "connect"))
        self.assertEqual(parse_qs(link.query), {"server": ["https://lims.example.com"]})

    def test_setup_needs_a_signed_in_person(self):
        for path in (SETUP_DOWNLOAD_PATH, SETUP_CONNECT_PATH):
            self.assertEqual(urlsplit(self.location(path)).path, "/web/login")

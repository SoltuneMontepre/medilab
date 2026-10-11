from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWebManifest(HttpCase):
    def test_manifest_uses_medilab_theme(self):
        response = self.url_open("/web/manifest.webmanifest")

        self.assertEqual(response.status_code, 200)
        manifest = response.json()
        self.assertEqual(manifest["theme_color"], "#0A4D8C")
        self.assertEqual(manifest["background_color"], "#F2F5F9")
        self.assertEqual([icon["sizes"] for icon in manifest["icons"]], ["192x192", "512x512"])

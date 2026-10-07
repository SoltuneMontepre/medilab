from odoo.addons.web.controllers.webmanifest import WebManifest

ICON_PATH = "analysis/static/src/theme/img/icons/icon-%s.png"
THEME_COLOR = "#1a2744"


class MedilabWebManifest(WebManifest):
    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest["background_color"] = THEME_COLOR
        manifest["theme_color"] = THEME_COLOR
        manifest["icons"] = [
            {"src": "/" + ICON_PATH % size, "sizes": size, "type": "image/png"} for size in ("192x192", "512x512")
        ]
        return manifest

    def _icon_path(self):
        return ICON_PATH % "192x192"

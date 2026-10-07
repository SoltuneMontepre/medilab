from odoo.addons.web.controllers.webmanifest import WebManifest

ICON_PATH = "laboratory/static/src/theme/img/icons/icon-%s.png"
THEME_COLOR = "#0A4D8C"
BACKGROUND_COLOR = "#F2F5F9"


class MedilabWebManifest(WebManifest):
    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest["background_color"] = BACKGROUND_COLOR
        manifest["theme_color"] = THEME_COLOR
        manifest["icons"] = [
            {"src": "/" + ICON_PATH % size, "sizes": size, "type": "image/png"} for size in ("192x192", "512x512")
        ]
        return manifest

    def _icon_path(self):
        return ICON_PATH % "192x192"

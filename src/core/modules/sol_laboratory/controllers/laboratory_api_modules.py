from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_MODULE_MODULE
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route

# The technical names of MediLab's own modules start with it.
MEDILAB_MODULE_PREFIX = "sol_"


class LaboratoryApiModules(http.Controller):
    """The installed MediLab modules, so an application shows only the screens of the modules installed."""

    @laboratory_api_route("/modules", ["GET"], "listModules", permission=False)
    def list_modules(self, device, _body):
        # Every person may know which modules are installed; reading them needs full rights, and only their names go out.
        modules = device.env[MODEL_IR_MODULE_MODULE].sudo().search([("state", "=", "installed")], order="name")
        return {"modules": [name for name in modules.mapped("name") if name.startswith(MEDILAB_MODULE_PREFIX)]}

from odoo import http
from odoo.http import request
from odoo.tools import str2bool

from odoo.addons.base.models.assetsbundle import ANY_UNIQUE
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.services.request_env import request_env
from odoo.addons.web.controllers.binary import Binary


def _readonly_unless_downloaded(controller, rule, args):
    # Downloading a file of an audited document writes an audit entry, which needs a read/write cursor.
    return not str2bool(request.httprequest.args.get("download") or "0", default=False)


class MedilabBinary(Binary):
    @http.route(readonly=_readonly_unless_downloaded)
    def content_common(self, *args, **kwargs):
        return super().content_common(*args, **kwargs)

    @http.route(readonly=_readonly_unless_downloaded)
    def content_image(self, *args, **kwargs):
        return super().content_image(*args, **kwargs)

    @http.route()
    def content_assets(self, filename=None, unique=ANY_UNIQUE, nocache=False, assets_params=None):
        # Odoo builds a bundle it has no attachment for, so a bundle whose file is lost loses its attachment first.
        request_env()[MODEL_IR_ATTACHMENT]._drop_lost_asset_bundle(filename, unique, assets_params or {})
        return super().content_assets(filename=filename, unique=unique, nocache=nocache, assets_params=assets_params)

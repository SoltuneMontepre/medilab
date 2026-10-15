from odoo import http
from odoo.http import request
from odoo.tools import str2bool

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

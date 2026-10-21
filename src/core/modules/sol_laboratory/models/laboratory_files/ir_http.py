from werkzeug.exceptions import MethodNotAllowed

from odoo import api, models
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_HTTP
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.laboratory_api import exception_answer, is_api_path


# Định Tuyến HTTP: every refusal and error on a path of the laboratory files API is answered in the API's own format.
class IrHttp(models.AbstractModel):
    _inherit = MODEL_IR_HTTP

    @classmethod
    def _match(cls, path_info):
        # A method the route does not take is refused while matching, before any route runs, so it is answered here.
        try:
            return super()._match(path_info)
        except MethodNotAllowed as error:
            if is_api_path(path_info):
                error.error_response = exception_answer(error)
            raise

    @classmethod
    def _handle_error(cls, exception):
        if is_api_path(request.httprequest.path):
            return exception_answer(exception)
        return super()._handle_error(exception)

    @api.model
    def _laboratory_files_ready_checks(self):
        """The checks of the parts the laboratory files API needs, by name: each returns whether its part serves. A
        feature that adds such a part adds its check; the editing service is never one, as only online editing needs
        it."""
        return {"database": self._laboratory_files_database_ready, "bucket": laboratory_bucket.is_ready}

    @api.model
    def _laboratory_files_database_ready(self):
        self.env.cr.execute("SELECT 1")
        return self.env.cr.fetchone() == (1,)

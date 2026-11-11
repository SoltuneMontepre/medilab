import logging

from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_HTTP
from odoo.addons.sol_laboratory.services.laboratory_api import UNAUTHENTICATED, json_answer, laboratory_api_route
from odoo.addons.sol_laboratory.services.request_env import request_env

_logger = logging.getLogger(__name__)

PASS = "pass"
FAIL = "fail"
# Health answers are about now; nothing keeps them.
NO_STORE = [("Cache-Control", "no-store")]


class LaboratoryApiStatus(http.Controller):
    """The health and readiness of the laboratory files API, for monitoring and for computers before they sync."""

    @laboratory_api_route("/health", ["GET"], "health", auth=UNAUTHENTICATED, readonly=True)
    def health(self, _body):
        return json_answer({"status": PASS}, headers=NO_STORE)

    @laboratory_api_route("/ready", ["GET"], "ready", auth=UNAUTHENTICATED, readonly=True)
    def ready(self, _body):
        checks = {}
        for name, check in request_env()[MODEL_IR_HTTP]._laboratory_files_ready_checks().items():
            try:
                checks[name] = PASS if check() else FAIL
            except Exception:
                _logger.warning("The readiness check %s of the laboratory files API failed.", name, exc_info=True)
                checks[name] = FAIL
        status = FAIL if FAIL in checks.values() else PASS
        return json_answer({"status": status, "checks": checks}, 200 if status == PASS else 503, NO_STORE)

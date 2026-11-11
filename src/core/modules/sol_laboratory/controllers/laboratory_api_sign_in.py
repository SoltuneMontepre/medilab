from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_REVOKED, INVALID_CREDENTIALS, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_LABORATORY_SIGN_IN_ATTEMPT
from odoo.addons.sol_laboratory.services.laboratory_api import BY_LOGIN, laboratory_api_route, refusal_answer
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.request_env import request_env


class LaboratoryApiSignIn(http.Controller):
    """Signing computers in to the laboratory files with the person's MediLab login, and out."""

    @laboratory_api_route("/sign-in", ["POST"], "signIn", auth=BY_LOGIN)
    def sign_in(self, body):
        env = request_env()
        attempts = env[MODEL_LABORATORY_SIGN_IN_ATTEMPT].sudo()
        login = body["login"]
        attempts._check_delay(login)
        attempts._check_address_cooldown(request.httprequest.remote_addr)
        try:
            with env.cr.savepoint():
                device, key = env[MODEL_LABORATORY_DEVICE]._sign_in(
                    login, body["password"], body["client_uid"], body["name"], body["platform"]
                )
        except LaboratoryFileError as refusal:
            if refusal.code == INVALID_CREDENTIALS:
                attempts._record_failure(login)
            elif refusal.code in (PERMISSION_DENIED, DEVICE_REVOKED):
                # The password was right.
                attempts._clear(login)
            else:
                raise
            # Answered rather than raised, so what it counted is committed.
            return refusal_answer(refusal.code, refusal.args[0])
        attempts._clear(login)
        return {"key": key, "device": device._laboratory_api_values(device)}

    @laboratory_api_route("/sign-out", ["POST"], "signOut", permission=False)
    def sign_out(self, device, _body):
        # A person who lost the laboratory files permission still signs their computers out.
        device._sign_out()

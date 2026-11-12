from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_TASK
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route


class LaboratoryApiMe(http.Controller):
    """The person signed in on Medilab Mobile and what they may do, so the app shows what the web shows them."""

    @laboratory_api_route("/me", ["GET"], "getMe", permission=False)
    def get_me(self, device, _body):
        env = device.env
        # The person reads their own department and roles, which only administrators read of other people.
        person = env[MODEL_PERSON]._current()
        tasks = env[MODEL_TASK]
        return {
            "name": person.name or env.user.name,
            "login": env.user.login,
            "department": person.department_id.name or "",
            "roles": person.role_ids.mapped("name"),
            "can": {"create_tasks": tasks._may_create(), "assign_tasks": tasks._may_assign()},
        }

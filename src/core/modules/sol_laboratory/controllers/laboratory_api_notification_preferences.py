from odoo import http
from odoo.exceptions import MissingError

from odoo.addons.sol_laboratory.constants.medilab_mobile import MANDATORY_EVENT
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE_SUBTYPE, MODEL_NOTIFICATION_PREFERENCE
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_PUSH
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


def preference_values(event, push):
    return {"event": event.code, "name": event.name or "", "mandatory": event.mandatory, "push": push}


class LaboratoryApiNotificationPreferences(http.Controller):
    """Which events Medilab Mobile pushes to the person: their push preferences, the ones the web shows."""

    @laboratory_api_route("/notification-preferences", ["GET"], "listNotificationPreferences", permission=False)
    def list_preferences(self, device, _body):
        choices = device.env[MODEL_NOTIFICATION_PREFERENCE]._push_choices()
        return {"preferences": [preference_values(event, push) for event, push in choices]}

    @laboratory_api_route(
        "/notification-preferences/<string:event_code>", ["PUT"], "setNotificationPreference", permission=False
    )
    def set_preference(self, device, body, event_code):
        env = device.env
        # Only an event that notifies people: an event the administrator turned off has no push to choose.
        event = env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(event_code).with_env(env)
        if not event:
            raise MissingError(env._("Nothing is found at this address."))
        if event.mandatory and not body["push"]:
            raise LaboratoryFileError(MANDATORY_EVENT, env._("A mandatory event cannot be turned off."))
        env[MODEL_NOTIFICATION_PREFERENCE].set_own(event, CHANNEL_PUSH, body["push"])
        return preference_values(event, body["push"] or event.mandatory)

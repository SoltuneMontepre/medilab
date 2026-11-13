"""The documents Medilab Mobile opens: from a push, a notification or a task."""

from odoo.api import Environment
from odoo.exceptions import MissingError

from odoo.addons.sol_laboratory.constants.medilab_mobile import CONVERSATION_SCREEN, WEB_SCREEN
from odoo.addons.sol_laboratory.constants.models import MODEL_DISCUSS_CHANNEL
from odoo.addons.sol_laboratory.services.document_code import document_code
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model


def not_found(env: Environment) -> MissingError:
    return MissingError(env._("Nothing is found at this address."))


def document_screen(records) -> str:
    """The app's screen for documents of the model; web for a model the app has no screen of its own for."""
    screen = getattr(records, "_mobile_screen", None)
    if screen:
        return screen
    return CONVERSATION_SCREEN if records._name == MODEL_DISCUSS_CHANNEL else WEB_SCREEN


def document_values(env: Environment, model: str, record_id: int):
    """The document as the person may read it: its code, its title, the app's screen for it and its address on the web.
    A document that does not exist, or that the person may not read, raises MissingError or AccessError, which the API
    answers as not found, so the answer does not tell that it exists."""
    if model not in env:
        raise not_found(env)
    records = dynamic_model(env, model)
    if records._abstract or records._transient:
        raise not_found(env)
    record = records.browse(record_id).exists()
    if not record:
        raise not_found(env)
    record.check_access("read")
    code = document_code(record)
    screen = document_screen(record)
    # The web client reads a model name without a dot only with its m- prefix.
    web_path = model if "." in model else f"m-{model}"
    return {
        "model": model,
        "id": record.id,
        "code": code,
        "title": code or record.display_name or "",
        "screen": screen,
        "url": f"{record.get_base_url()}/odoo/{web_path}/{record.id}",
    }

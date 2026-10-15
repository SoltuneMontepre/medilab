from odoo.api import Environment
from odoo.http import request


def request_env() -> Environment:
    """The environment of the current request.

    Odoo types request.env as optional, because a request may have no database. Routes that need one read it here.
    """
    if request.env is None:
        raise RuntimeError("The request has no database.")
    return request.env

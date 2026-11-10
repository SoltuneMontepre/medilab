"""Phones signed in on Medilab Mobile and their push tokens, for tests that need them without calling the API."""

import uuid

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_MOBILE_DEVICE


def signed_in_phone(env, user, name="Galaxy A55", platform="android"):
    """A new phone of the user signed in as signing in from Medilab Mobile makes it, and its key."""
    devices = env[MODEL_LABORATORY_DEVICE].with_user(user)
    key, key_id = devices._new_key(name, phone=True)
    phone = devices.sudo().create(
        {"user_id": user.id, "client_uid": uuid.uuid4().hex, "name": name, "platform": platform, "api_key_id": key_id}
    )
    return phone, key


def push_token(env, user, token, platform="android"):
    """The push token of a new phone of the user, registered and on."""
    phone, _key = signed_in_phone(env, user, platform=platform)
    return env[MODEL_MOBILE_DEVICE]._register_token(phone, token)

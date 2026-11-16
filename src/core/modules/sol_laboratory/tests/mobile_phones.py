"""Phones signed in on Medilab Mobile and their push tokens, for tests that need them without calling the API, and the
people who sign them in."""

import uuid

from odoo.fields import Command

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_MOBILE_DEVICE,
    MODEL_PERMISSION,
    MODEL_PERSON,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id


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


def phone_person(env, name, login, department, permissions):
    """A person of the department, or of none, with a login, the test password and the permissions of the codes, such
    as sample_read_all."""
    person = env[MODEL_PERSON].create(
        {
            "name": name,
            "login": login,
            "department_id": department.id if department else False,
            "permission_ids": [
                Command.set(
                    [
                        persisted_id(reference_as(env[MODEL_PERMISSION], f"sol_laboratory.permission_{code}"))
                        for code in permissions
                    ]
                )
            ],
        }
    )
    person.user_id.password = PASSWORD
    return person


class PhoneCalls(LaboratoryApiCase):
    """Calls of Medilab Mobile made by people, each on a phone of their own signed in once."""

    def setUp(self):
        super().setUp()
        self.keys = {}

    def on_phone(self, person, method, path, body=None, headers=None):
        if person not in self.keys:
            self.keys[person] = self.signed_in_key(
                person.user_id, f"phone-{person.id}", name="Pixel 8", platform="android"
            )
        return self.api(method, path, body, key=self.keys[person], headers=headers)

    def answered(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

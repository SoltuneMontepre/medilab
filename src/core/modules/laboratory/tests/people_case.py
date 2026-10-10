from odoo.fields import Command
from odoo.tests import TransactionCase

from odoo.addons.laboratory.constants.models import MODEL_DEPARTMENT, MODEL_PERMISSION, MODEL_PERSON


class PeopleCase(TransactionCase):
    """Chemistry and Microbiology, with a person in each who signs in."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chemistry, cls.microbiology = cls.env[MODEL_DEPARTMENT].create(
            [{"name": "Chemistry"}, {"name": "Microbiology"}]
        )
        cls.chemist = cls.create_person("Nguyen Van An", cls.chemistry, "an.nguyen")
        cls.microbiologist = cls.create_person("Tran Thi Binh", cls.microbiology, "binh.tran")

    @classmethod
    def create_person(cls, name, department=None, login=None, permissions=(), roles=None):
        vals = {"name": name, "department_id": department.id if department else False}
        if login:
            vals["login"] = login
        if permissions:
            vals["permission_ids"] = [Command.set(cls.permissions(*permissions).ids)]
        if roles:
            vals["role_ids"] = [Command.set(roles.ids)]
        return cls.env[MODEL_PERSON].create(vals)

    @classmethod
    def permissions(cls, *codes):
        return cls.env[MODEL_PERMISSION].concat(
            cls.env.ref(f"laboratory.permission_{code.replace('.', '_')}") for code in codes
        )

    @classmethod
    def grant(cls, person, *codes):
        person.permission_ids = [Command.link(permission.id) for permission in cls.permissions(*codes)]

    @staticmethod
    def as_person(records, person):
        return records.with_user(person.user_id)

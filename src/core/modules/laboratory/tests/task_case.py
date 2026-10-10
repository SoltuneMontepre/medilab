from datetime import timedelta

from odoo import fields

from .people_case import PeopleCase
from odoo.addons.laboratory.constants.models import MODEL_ROLE, MODEL_TASK, MODEL_TASK_TYPE

SAMPLE_RECEIVED = "sample_received"
SIGNATURE_REQUESTED = "signature_requested"


class TaskCase(PeopleCase):
    """A department-routed testing task type, a role-routed signing task type and the shipped general task type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.signer_role = cls.env[MODEL_ROLE].create({"code": "signer", "name": "Signer"})
        cls.testing, cls.signing = cls.env[MODEL_TASK_TYPE].create(
            [
                {
                    "code": "testing",
                    "name": "Testing a parameter",
                    "trigger": SAMPLE_RECEIVED,
                    "document_model": "medilab.department",
                    "action": "enter_result",
                    "route": "department",
                    "deadline_hours": 48,
                },
                {
                    "code": "signing",
                    "name": "Signing a document",
                    "trigger": SIGNATURE_REQUESTED,
                    "route": "role",
                    "role_id": cls.signer_role.id,
                },
            ]
        )
        cls.general = cls.env.ref("laboratory.task_type_general")
        cls.tasks = cls.env[MODEL_TASK]
        cls.tomorrow = fields.Datetime.now() + timedelta(days=1)

    @classmethod
    def receive_sample(cls, department):
        return cls.tasks._create_for_event(SAMPLE_RECEIVED, department, department=department)

    @classmethod
    def create_by_hand(cls, assignee, **vals):
        return cls.tasks.create(
            {
                "type_id": cls.general.id,
                "name": "Call the customer",
                "assignee_id": assignee.id,
                "deadline": cls.tomorrow,
                **vals,
            }
        )

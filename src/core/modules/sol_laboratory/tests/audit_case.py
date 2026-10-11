from odoo.fields import Command
from odoo.tests import new_test_user

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_REGULATION


class AuditCase(MasterDataCase):
    """A master data editor, an auditor and a regulation with a limit for the parameter."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(cls.env, login="editor", groups="base.group_user,base.group_system")
        cls.auditor = new_test_user(
            cls.env, login="auditor", groups="base.group_user,sol_laboratory.group_permission_audit_entry_read_all"
        )
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {
                "code": "QCVN 8-2:2011/BYT",
                "name": "Limits of heavy metals in food",
                "limit_ids": [
                    Command.create(
                        {"parameter_id": cls.parameter.id, "unit_id": cls.unit.id, "max_value": 0.01, "decimals": 3}
                    )
                ],
            }
        )
        cls.limit = cls.regulation.limit_ids

    @classmethod
    def entries(cls, records, action=None):
        domain = [("document_model", "=", records._name), ("document_id", "in", records.ids)]
        if action:
            domain.append(("action", "=", action))
        return cls.env[MODEL_AUDIT_ENTRY].sudo().search(domain)

    @staticmethod
    def changes(entry):
        return {change.field_name: (change.old_value, change.new_value) for change in entry.change_ids}

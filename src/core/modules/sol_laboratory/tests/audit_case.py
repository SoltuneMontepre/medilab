from odoo.fields import Command
from odoo.tests import new_test_user

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_AUDIT_MIXIN, MODEL_REGULATION
from odoo.addons.sol_laboratory.constants.xml_ids import AUDIT_READ_GROUP

AUDITOR_GROUPS = f"base.group_user,{AUDIT_READ_GROUP}"


class AuditLookup:
    """Finds the audit entries of records and the changes of an entry, for any test case."""

    @classmethod
    def new_auditor(cls):
        return new_test_user(cls.env, login="auditor", groups=AUDITOR_GROUPS)

    @classmethod
    def unaudited_documents(cls, module):
        """The stored models the module defines or extends that do not inherit the audit mixin."""
        mixin = cls.env.registry[MODEL_AUDIT_MIXIN]
        return {
            name
            for name, model in cls.env.registry.items()
            if not model._abstract
            and not model._transient
            and not issubclass(model, mixin)
            and any(
                getattr(base, "_name", None) == name and getattr(base, "_module", None) == module
                for base in model.__mro__
            )
        }

    @classmethod
    def entries(cls, records, action=None):
        domain = [("document_model", "=", records._name), ("document_id", "in", records.ids)]
        if action:
            domain.append(("action", "=", action))
        return cls.env[MODEL_AUDIT_ENTRY].sudo().search(domain)

    @staticmethod
    def changes(entry):
        return {change.field_name: (change.old_value, change.new_value) for change in entry.change_ids}

    @classmethod
    def history(cls, document, user):
        """The entries the user finds in the document's history."""
        return cls.env[MODEL_AUDIT_ENTRY].with_user(user).search(document.action_open_audit_history()["domain"])


class AuditCase(AuditLookup, MasterDataCase):
    """A master data editor without the audit permission, an auditor and a regulation with a limit for the parameter."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(
            cls.env,
            login="editor",
            groups="base.group_user,base.group_system,sol_laboratory.group_permission_regulation_limit_edit_all",
        )
        cls.auditor = cls.new_auditor()
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {
                "code": "QCVN 8-2:2011/BYT",
                "name": "Limits of heavy metals in food",
                "limit_ids": [
                    Command.create(
                        {
                            "parameter_id": cls.parameter.id,
                            "unit_id": cls.unit.id,
                            "max_set": True,
                            "max_value": 0.01,
                            "decimals": 3,
                        }
                    )
                ],
            }
        )
        cls.limit = cls.regulation.limit_ids

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_IR_CRON,
    MODEL_RES_GROUPS,
    MODEL_TEST_PARAMETER,
)
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model, model_as, reference_as


@tagged("post_install", "-at_install")
class TestModelLookup(TransactionCase):
    def test_dynamic_lookup_preserves_the_model_and_rejects_an_absent_name(self):
        self.assertEqual(dynamic_model(self.env, MODEL_TEST_PARAMETER), self.env[MODEL_TEST_PARAMETER])
        with self.assertRaises(KeyError):
            dynamic_model(self.env, False)

    def test_an_inherited_mixin_can_be_required_without_changing_the_recordset(self):
        self.assertEqual(
            model_as(self.env, MODEL_TEST_PARAMETER, self.env[MODEL_AUDIT_MIXIN]),
            self.env[MODEL_TEST_PARAMETER],
        )
        with self.assertRaises(TypeError):
            model_as(self.env, MODEL_IR_CRON, self.env[MODEL_AUDIT_MIXIN])

    def test_references_keep_their_model_and_missing_reference_policy(self):
        groups = self.env[MODEL_RES_GROUPS]
        self.assertEqual(reference_as(groups, "base.group_system"), self.env.ref("base.group_system"))
        self.assertIsNone(reference_as(groups, "sol_laboratory.missing_typing_reference", False))
        with self.assertRaises(TypeError):
            reference_as(self.env[MODEL_TEST_PARAMETER], "base.group_system")

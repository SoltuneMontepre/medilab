from odoo.tests import TransactionCase, tagged

MODULE_PREFIX = "sol_"


@tagged("post_install", "-at_install")
class TestActionPaths(TransactionCase):
    def test_every_page_action_has_a_path(self):
        data = self.env["ir.model.data"].search(
            [("module", "=like", f"{MODULE_PREFIX}%"), ("model", "=", "ir.actions.act_window")]
        )
        actions = self.env["ir.actions.act_window"].browse(data.mapped("res_id"))

        missing = actions.filtered(lambda action: action.target != "new" and not action.path)

        self.assertFalse(missing, f"Window actions without a path: {sorted(missing.get_external_id().values())}")

import os
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_demo import hooks
from odoo.addons.sol_demo.bootstrap import BOOTSTRAP_MODE_VARIABLE, BOOTSTRAP_OWNER_VARIABLE, bootstrap_state


@tagged("post_install", "-at_install")
class TestDemoBootstrap(TransactionCase):
    def test_explicit_bootstrap_install_records_pending_without_seeding(self):
        owner = "00000000-0000-4000-8000-000000000001"
        with (
            patch.dict(
                os.environ,
                {BOOTSTRAP_MODE_VARIABLE: "1", BOOTSTRAP_OWNER_VARIABLE: owner},
            ),
            patch.object(hooks, "seed_demo") as seed,
        ):
            hooks.post_init_hook(self.env)

        seed.assert_not_called()
        self.assertEqual(bootstrap_state(self.env), {"owner": owner, "status": "pending"})

    def test_install_without_bootstrap_mode_keeps_the_standard_seed_hook(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(hooks, "seed_demo") as seed,
        ):
            hooks.post_init_hook(self.env)

        seed.assert_called_once_with(self.env)

    def test_bootstrap_install_requires_an_owner_id(self):
        with (
            patch.dict(os.environ, {BOOTSTRAP_MODE_VARIABLE: "1", BOOTSTRAP_OWNER_VARIABLE: "invalid"}),
            patch.object(hooks, "seed_demo") as seed,
            self.assertRaises(ValueError),
        ):
            hooks.post_init_hook(self.env)

        seed.assert_not_called()

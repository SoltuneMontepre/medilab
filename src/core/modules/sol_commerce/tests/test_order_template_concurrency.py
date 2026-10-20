from unittest.mock import patch
from uuid import uuid4

from psycopg2.errors import SerializationFailure

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.modules.registry import Registry
from odoo.tests import BaseCase, tagged
from odoo.tests.common import get_db_name


@tagged("post_install", "-at_install")
class TestOrderTemplateConcurrency(BaseCase):
    def template_fixture(self):
        registry = Registry(get_db_name())
        # Installation may advance the in-process registry counter before real cursors see its commit.
        with registry.cursor() as cr:
            sequence, _caches = registry.get_sequences(cr)
        self.startPatcher(patch.object(registry, "registry_sequence", sequence))
        key = uuid4().hex[:10]

        def cleanup():
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
                customer = env["medilab.customer"].search([("name", "=", f"Race customer {key}")])
                templates = env["medilab.order.template"].search([("customer_id", "in", customer.ids)])
                templates.unlink()
                env["sale.order"].search([("customer_id", "in", customer.partner_id.ids)]).unlink()
                parameter = env["medilab.test.parameter"].search([("name", "=", f"Race lead {key}")])
                package = env["medilab.service.package"].search([("code", "=", key)])
                env["product.template"].search(
                    [
                        "|",
                        ("parameter_id", "in", parameter.ids),
                        ("service_package_id", "in", package.ids),
                    ]
                ).unlink()
                package.unlink()
                env["medilab.parameter.price"].search([("parameter_id", "in", parameter.ids)]).unlink()
                parameter.unlink()
                env["medilab.tax"].search([("code", "=", key)]).unlink()
                env["medilab.parameter.group"].search([("name", "=", f"Template race {key}")]).unlink()
                partner = customer.partner_id
                customer.unlink()
                partner.exists().unlink()

        self.addCleanup(cleanup)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            group = env["medilab.parameter.group"].create({"name": f"Template race {key}"})
            parameter = env["medilab.test.parameter"].create(
                {"name": f"Race lead {key}", "main_group_id": group.id, "group_ids": [Command.set(group.ids)]}
            )
            tax = env["medilab.tax"].create({"name": f"Race tax {key}", "code": key})
            price = env["medilab.parameter.price"].create(
                {"parameter_id": parameter.id, "list_price": 150000, "tax_id": tax.id}
            )
            package = env["medilab.service.package"].create(
                {
                    "name": f"Race package {key}",
                    "code": key,
                    "list_price": 100000,
                    "tax_id": tax.id,
                    "line_ids": [Command.create({"parameter_id": parameter.id, "quantity": 1})],
                }
            )
            customer = env["medilab.customer"].create({"name": f"Race customer {key}"})
            products = env["product.template"].search(
                ["|", ("parameter_id", "=", parameter.id), ("service_package_id", "=", package.id)]
            )
            source = (
                env["sale.order"]
                .with_context(medilab_sales_order=True)
                .create(
                    {
                        "partner_id": customer.partner_id.id,
                        "customer_id": customer.partner_id.id,
                        "order_line": [
                            Command.create({"product_id": product.product_variant_ids.id, "product_uom_qty": 1})
                            for product in products
                        ],
                    }
                )
            )
            source._set_status("completed")
            template = source._save_as_template(f"Race template {key}")
            template_id, price_id, package_id = template.id, price.id, package.id
        return registry, template_id, price_id, package_id

    def test_concurrent_catalog_change_uses_one_snapshot_and_later_reuse_sees_the_change(self):
        registry, template_id, price_id, package_id = self.template_fixture()
        with registry.cursor() as read_cr:
            env = api.Environment(read_cr, SUPERUSER_ID, {})
            template = env["medilab.order.template"].browse(template_id)
            self.assertEqual(template.line_ids.product_id.mapped("list_price"), [150000, 100000])
            with registry.cursor() as write_cr:
                writer = api.Environment(write_cr, SUPERUSER_ID, {})
                writer["medilab.parameter.price"].browse(price_id).list_price = 160000
                writer["medilab.service.package"].browse(package_id).action_archive()
            order = template._create_order()
            self.assertEqual(order.amount_untaxed, 250000)
            self.assertFalse(order.template_omission_note)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            template = env["medilab.order.template"].browse(template_id)
            order = template._create_order()
            self.assertEqual(order.amount_untaxed, 160000)
            self.assertEqual(len(order._catalog_lines()), 1)
            self.assertIn("Race package", order.template_omission_note)

    def test_concurrent_line_deletions_cannot_empty_template(self):
        registry, template_id, _price_id, _package_id = self.template_fixture()
        with registry.cursor() as first_cr, registry.cursor() as second_cr:
            first = api.Environment(first_cr, SUPERUSER_ID, {})
            second = api.Environment(second_cr, SUPERUSER_ID, {})
            first_lines = first["medilab.order.template"].browse(template_id).line_ids
            second_lines = second["medilab.order.template"].browse(template_id).line_ids
            self.assertEqual(first_lines.ids, second_lines.ids)
            self.assertEqual(len(first_lines), 2)
            first_lines[:1].unlink()
            first_cr.commit()
            with self.assertRaises(SerializationFailure):
                second_lines[1:].unlink()
            second_cr.rollback()
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            lines = env["medilab.order.template"].browse(template_id).line_ids
            self.assertEqual(len(lines), 1)
            with self.assertRaises(ValidationError):
                lines.unlink()
            self.assertTrue(lines.exists())

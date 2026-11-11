from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .template_case import TemplateCase
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestOrderTemplateIntegrity(TemplateCase):
    def template_values(self, source, **values):
        return {
            "name": "ORM selection",
            "source_order_id": source.id,
            "customer_id": self.customer_record.id,
            **values,
        }

    def record_counts(self):
        return tuple(
            self.env[model].search_count([])
            for model in (
                "medilab.order.template",
                "medilab.order.template.line",
                "medilab.audit.entry",
            )
        )

    def test_direct_non_admin_create_requires_initial_selections(self):
        source = self.template_source()
        templates = self.env["medilab.order.template"].with_user(self.sales)
        self.assertFalse(templates.env.su)
        for values in ({}, {"line_ids": []}, {"line_ids": False}):
            with self.subTest(values=values):
                before = self.record_counts()
                with self.assertRaises(ValidationError):
                    templates.create(self.template_values(source, **values))
                self.assertEqual(self.record_counts(), before)

    def test_invalid_initial_product_rolls_back_headers_lines_and_audit(self):
        source = self.template_source()
        ordinary = self.env["product.template"].create({"name": "Non-catalog service", "type": "service"})
        valid = Command.create({"product_id": self.lead_product.id, "quantity": 2})
        invalid = Command.create({"product_id": ordinary.id, "quantity": 2})
        before = self.record_counts()
        with self.assertRaises(ValidationError):
            self.env["medilab.order.template"].with_user(self.sales).create(
                [
                    self.template_values(source, line_ids=[valid]),
                    self.template_values(source, line_ids=[valid, invalid]),
                ]
            )
        self.assertEqual(self.record_counts(), before)

    def test_invalid_initial_quantity_rolls_back_headers_lines_and_audit(self):
        source = self.template_source()
        for quantity in (0, 1.5, None, "invalid", float("nan"), float("inf"), -float("inf")):
            with self.subTest(quantity=quantity):
                before = self.record_counts()
                with self.assertRaises(ValidationError):
                    self.env["medilab.order.template"].with_user(self.sales).create(
                        self.template_values(
                            source,
                            line_ids=[
                                Command.create({"product_id": self.lead_product.id, "quantity": 2}),
                                Command.create({"product_id": self.package_product.id, "quantity": quantity}),
                            ],
                        )
                    )
                self.assertEqual(self.record_counts(), before)

    def test_parent_commands_cannot_remove_every_selection_and_roll_back_other_edits(self):
        for operation in ("clear", "set", "delete", "unlink"):
            with self.subTest(operation=operation):
                template = self.save_template()
                lines, name, before = template.line_ids, template.name, self.record_counts()
                commands = {
                    "clear": [Command.clear()],
                    "set": [Command.set([])],
                    "delete": [Command.delete(persisted_id(line)) for line in lines],
                    "unlink": [Command.unlink(persisted_id(line)) for line in lines],
                }[operation]
                with self.assertRaises(ValidationError):
                    template.with_user(self.sales).write({"name": "Should roll back", "line_ids": commands})
                self.assertEqual(template.name, name)
                self.assertEqual(template.line_ids, lines)
                self.assertEqual(self.record_counts(), before)

    def test_direct_line_delete_and_reparent_cannot_empty_source_template(self):
        source = self.template_source([(self.lead_product, 2)])
        template = self.save_template(source)
        target = self.save_template()
        line = template.line_ids
        before = self.record_counts()
        with self.assertRaises(ValidationError):
            line.with_user(self.sales).with_context(editing_template_ids=template.ids).unlink()
        self.assertEqual(template.line_ids, line)
        with self.assertRaises(ValidationError):
            line.with_user(self.sales).write({"template_id": target.id})
        self.assertEqual(line.template_id, template)
        self.assertEqual(self.record_counts(), before)

    def test_atomic_replacement_and_nonempty_reparenting_remain_supported(self):
        template = self.save_template()
        target = self.save_template()
        moved = template.line_ids[:1]
        moved.with_user(self.sales).write({"template_id": target.id})
        self.assertEqual(len(template.line_ids), 1)
        self.assertEqual(len(target.line_ids), 3)
        template.with_user(self.sales).write(
            {
                "line_ids": [
                    Command.clear(),
                    Command.create({"product_id": self.lead_product.id, "quantity": 4}),
                ]
            }
        )
        self.assertEqual(template.line_ids.product_id, self.lead_product)
        self.assertEqual(template.line_ids.quantity, 4)

    def test_invalid_replacement_rolls_back_parent_selections_and_audit(self):
        template = self.save_template()
        ordinary = self.env["product.template"].create({"name": "Invalid replacement", "type": "service"})
        lines, name, before = template.line_ids, template.name, self.record_counts()
        with self.assertRaises(ValidationError):
            template.with_user(self.sales).write(
                {
                    "name": "Should roll back",
                    "line_ids": [
                        Command.clear(),
                        Command.create({"product_id": ordinary.id, "quantity": 2}),
                    ],
                }
            )
        self.assertEqual(template.name, name)
        self.assertEqual(template.line_ids, lines)
        self.assertEqual(self.record_counts(), before)

    def test_new_line_identities_are_checked_without_revalidating_retired_history(self):
        source = self.template_source()
        template = self.save_template(source)
        ordinary = self.env["product.template"].create({"name": "Other service", "type": "service"})
        lines = template.line_ids
        before = self.record_counts()
        with self.assertRaises(ValidationError):
            self.env["medilab.order.template.line"].with_user(self.sales).create(
                {
                    "template_id": template.id,
                    "product_id": ordinary.id,
                    "quantity": 1,
                }
            )
        with self.assertRaises(ValidationError):
            lines[:1].with_user(self.sales).write({"product_id": ordinary.id})
        self.assertEqual(template.line_ids, lines)
        self.assertEqual(lines[:1].product_id, self.lead_product)
        self.assertEqual(self.record_counts(), before)
        source._set_status("completed")
        self.lead_price.action_archive()
        self.package.action_archive()
        template.with_user(self.sales).write({"name": "Retired selections"})
        lines.with_user(self.sales).write({"quantity": 4})
        historical = self.save_template(source)
        self.assertEqual(historical.line_ids.product_id, lines.product_id)
        self.assertEqual(historical.line_ids.mapped("quantity"), [2, 3])
        with self.assertRaises(ValidationError):
            self.reuse(template)

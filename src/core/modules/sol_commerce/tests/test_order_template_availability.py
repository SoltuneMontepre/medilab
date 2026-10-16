from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .template_case import TemplateCase


@tagged("post_install", "-at_install")
class TestOrderTemplateAvailability(TemplateCase):
    def retired_source(self):
        source = self.template_source()
        template = self.save_template(source)
        source._set_status("completed")
        return template

    def test_current_package_contents_replace_historical_components(self):
        template = self.retired_source()
        self.package.line_ids.filtered(lambda line: line.parameter_id == self.other).unlink()
        order = self.reuse(template)
        package = order._catalog_lines().filtered(lambda line: line.product_id.product_tmpl_id == self.package_product)
        self.assertEqual(package.linked_line_ids.product_id.product_tmpl_id, self.lead_product)
        self.assertEqual(package.linked_line_ids.product_uom_qty, 2.25)
        self.assertEqual(package.linked_line_ids.price_unit, 0)

    def test_partial_unavailability_is_persisted_on_order(self):
        template = self.retired_source()
        self.package.action_archive()
        order = self.reuse(template)
        self.assertEqual(order._catalog_lines().product_id.product_tmpl_id, self.lead_product)
        self.assertIn(self.package_product.name, order.template_omission_note)
        self.assertTrue(order.template_omission_note.split(":")[-1].strip())
        order.invalidate_recordset()
        self.assertIn(
            self.package_product.name,
            order.with_user(self.sales).read(["template_omission_note"])[0]["template_omission_note"],
        )

    def test_unavailable_component_skips_entire_package(self):
        template = self.retired_source()
        self.other_price.action_archive()
        order = self.reuse(template)
        self.assertEqual(order._catalog_lines().product_id.product_tmpl_id, self.lead_product)
        self.assertFalse(order.order_line.linked_line_id)
        self.assertIn(self.package.name, order.template_omission_note)
        self.assertIn(self.other.name, order.template_omission_note)

    def test_all_unavailable_creates_no_order(self):
        template = self.retired_source()
        self.lead_price.action_archive()
        self.package.action_archive()
        before = self.env["sale.order"].search_count([])
        with self.assertRaises(ValidationError):
            self.reuse(template)
        self.assertEqual(self.env["sale.order"].search_count([]), before)

    def test_archived_product_or_variant_is_not_ordered(self):
        for field in ("product", "variant"):
            with self.subTest(field=field), self.cr.savepoint():
                source = self.template_source([(self.lead_product, 1)])
                template = self.save_template(source)
                source._set_status("completed")
                record = self.lead_product if field == "product" else self.lead_product.product_variant_ids
                record.active = False
                with self.assertRaises(ValidationError):
                    self.reuse(template)
                record.active = True

    def test_missing_parameter_or_empty_package_is_not_ordered(self):
        template = self.retired_source()
        self.lead_product.parameter_id = False
        self.package.line_ids.unlink()
        with self.assertRaises(ValidationError):
            self.reuse(template)

    def test_unexpected_package_failure_rolls_back_order_and_lines(self):
        template = self.save_template()
        before = self.env["sale.order"].search_count([]), self.env["sale.order.line"].search_count([])
        line_class = type(self.env["sale.order.line"])
        original = line_class._add_package_parts

        def fail_after_expansion(lines):
            original(lines)
            raise RuntimeError("Unexpected expansion failure")

        with patch.object(line_class, "_add_package_parts", fail_after_expansion):
            with self.assertRaises(RuntimeError):
                self.reuse(template)
        self.assertEqual(
            (self.env["sale.order"].search_count([]), self.env["sale.order.line"].search_count([])), before
        )

    def test_package_skips_component_whose_expansion_selects_an_archived_variant(self):
        template = self.retired_source()
        component = self.env["product.template"].search([("parameter_id", "=", self.other.id)])
        archived = component.product_variant_ids
        archived.active = False
        active = self.env["product.product"].create({"product_tmpl_id": component.id})
        self.assertTrue(active.active)
        self.assertEqual(component.with_context(active_test=False).product_variant_ids[:1], archived)
        order = self.reuse(template)
        self.assertEqual(order._catalog_lines().product_id.product_tmpl_id, self.lead_product)
        self.assertFalse(order.order_line.linked_line_id)
        self.assertIn(self.other.name, order.template_omission_note)

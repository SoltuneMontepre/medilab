from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .template_case import TemplateCase


@tagged("post_install", "-at_install")
class TestOrderTemplate(TemplateCase):
    def test_template_models_are_registered(self):
        self.assertIn("medilab.order.template", self.env)
        self.assertIn("medilab.order.template.line", self.env)

    def test_save_preserves_catalog_selections_and_fractional_quantities(self):
        source = self.template_source()
        source._catalog_lines().discount = 15
        template = self.save_template(source)
        self.assertEqual(template.customer_id, self.customer_record)
        self.assertEqual(template.source_order_id, source)
        self.assertEqual(
            [(line.product_id.id, line.quantity) for line in template.line_ids],
            [(self.lead_product.id, 1.5), (self.package_product.id, 2.25)],
        )
        self.assertEqual(len(source.order_line), 4)
        self.assertNotIn("price_unit", template.line_ids._fields)

    def test_valid_and_invalid_quantities_in_both_workflows(self):
        for quantity in (1, 1.5, 2.25):
            with self.subTest(quantity=quantity):
                template = self.save_template(self.template_source([(self.lead_product, quantity)]))
                self.assertEqual(template.line_ids.quantity, quantity)
                self.assertEqual(self.reuse(template)._catalog_lines().product_uom_qty, quantity)
        template = self.save_template(self.template_source([(self.lead_product, 1)]))
        for quantity in (0.5, 0, -1):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError), self.cr.savepoint():
                template.line_ids.write({"quantity": quantity})
            with self.subTest(source_quantity=quantity), self.assertRaises(ValidationError), self.cr.savepoint():
                self.template_source([(self.lead_product, quantity)])

    def test_blank_name_and_empty_order_are_rejected(self):
        source = self.template_source()
        with self.assertRaises(ValidationError):
            source.with_user(self.sales)._save_as_template("  ")
        source._catalog_lines().unlink()
        with self.assertRaises(ValidationError):
            self.save_template(source)

    def test_reuse_is_a_fresh_sales_draft_without_downstream_documents(self):
        source = self.template_source()
        source.write(
            {
                "advance_method": "cash",
                "advance_mode": "fixed",
                "advance_value": 10000,
                "expected_result_date": "2026-12-31",
                "payment_deadline": "2026-12-20 00:00:00",
            }
        )
        source._catalog_lines().discount = 20
        template = self.save_template(source)
        counts = {
            model: self.env[model].search_count([])
            for model in (
                "account.move",
                "account.payment",
                "payment.transaction",
                "medilab.test.request",
                "medilab.signature",
            )
        }
        order = self.reuse(template)
        self.assertEqual(
            (order.state, order.order_status, order.source, order.user_id), ("draft", "claimed", "sales", self.sales)
        )
        self.assertEqual(order.pipeline_stage, "draft")
        self.assertEqual(order.revenue, 0)
        self.assertTrue(order.claimed_at)
        for field in (
            "submitted_at",
            "quoted_at",
            "accepted_at",
            "confirmed_at",
            "payment_deadline",
            "expected_result_date",
            "quotation_ids",
            "sample_ids",
            "invoice_ids",
            "test_request_id",
            "advance_method",
            "reordered_from_id",
        ):
            self.assertFalse(order[field], field)
        self.assertEqual(order._catalog_lines().mapped("discount"), [0, 0])
        self.assertEqual(order.quotation_sent_count, 0)
        self.assertEqual(counts, {model: self.env[model].search_count([]) for model in counts})
        self.assertEqual(source._catalog_lines().mapped("discount"), [20, 20])

    def test_new_order_continues_through_the_normal_quotation_workflow(self):
        order = self.reuse(self.save_template())
        order._catalog_lines().sample_id = self.make_sample(order)
        order.write({"advance_method": "cash", "advance_mode": "full"})
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(len(order.quotation_ids), 1)
        self.assertEqual(len(order.invoice_ids), 1)
        self.assertEqual(order.state, "sent")

    def test_confirmed_source_is_only_read_and_does_not_freeze_template_edits(self):
        source = self.make_confirmed_order()
        template = self.save_template(source)
        template.with_user(self.sales).write({"name": "Updated selection"})
        template.line_ids.with_user(self.sales).write({"quantity": 2.25})
        order = self.reuse(template)
        self.assertEqual(order._catalog_lines().product_uom_qty, 2.25)
        self.assertEqual(source.order_status, "confirmed")
        self.assertEqual(source._catalog_lines().product_uom_qty, 1)

    def test_archived_template_cannot_be_reused(self):
        template = self.save_template()
        template.with_user(self.sales).action_archive()
        self.assertFalse(template.active)
        with self.assertRaises(ValidationError):
            self.reuse(template)
        template.with_user(self.sales).action_unarchive()
        self.assertTrue(self.reuse(template))

    def test_dialog_checks_source_and_saves_named_template(self):
        source = self.template_source()
        action = source.with_user(self.sales).action_save_as_template()
        wizard = (
            self.env[action["res_model"]]
            .with_user(self.sales)
            .with_context(**action["context"])
            .create({"name": "Water check"})
        )
        result = wizard.action_save()
        template = self.env["medilab.order.template"].browse(result["res_id"])
        self.assertEqual((template.name, template.source_order_id), ("Water check", source))
        with self.assertRaises(AccessError):
            source.with_user(self.other_sales).action_save_as_template()

    def test_caller_defaults_cannot_preconfirm_or_copy_historical_fields(self):
        template = (
            self.save_template()
            .with_user(self.sales)
            .with_context(
                default_state="sale",
                default_date_order="2020-01-01 00:00:00",
                default_expected_result_date="2020-01-01",
                default_advance_method="cash",
                default_payment_deadline="2020-01-02 00:00:00",
            )
        )
        result = template.action_create_order()
        order = self.env["sale.order"].browse(result["res_id"])
        self.assertEqual(order.state, "draft")
        self.assertGreater(order.date_order.year, 2020)
        self.assertFalse(order.advance_method or order.expected_result_date or order.payment_deadline)

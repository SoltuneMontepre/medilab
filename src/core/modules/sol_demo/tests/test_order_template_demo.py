from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrderTemplateDemo(TransactionCase):
    def test_template_examples_include_generated_order_and_archive(self):
        template = self.env.ref("sol_demo.demo_order_template_monthly_water", raise_if_not_found=False)
        if template is None:
            self.fail("The monthly water template must be seeded")
        archived = self.env.ref("sol_demo.demo_order_template_archived")
        order = self.env.ref("sol_demo.demo_sale_order_from_template")
        self.assertEqual(template.name, "Monthly water check")
        self.assertTrue(template.line_ids.product_id.parameter_id)
        self.assertTrue(template.line_ids.product_id.service_package_id)
        self.assertFalse(archived.active)
        self.assertEqual((order.state, order.order_status, order.source), ("draft", "claimed", "sales"))
        self.assertEqual(order.customer_id, template.customer_id.partner_id)
        self.assertEqual(order._catalog_lines().mapped("product_uom_qty"), template.line_ids.mapped("quantity"))
        lead = template.line_ids.filtered(lambda line: bool(line.product_id.parameter_id))
        self.assertEqual(lead.quantity, 2)
        self.assertTrue(
            all(float(quantity).is_integer() for quantity in order._catalog_lines().mapped("product_uom_qty"))
        )

    def test_repeat_seeding_preserves_existing_records_and_role_grants(self):
        from odoo.addons.sol_demo.demo_order_templates import seed_order_templates

        template = self.env.ref("sol_demo.demo_order_template_monthly_water")
        order = self.env.ref("sol_demo.demo_sale_order_from_template")
        template.write({"name": "Customer-edited template"})
        order._catalog_lines()[:1].write({"product_uom_qty": 3})
        seed_order_templates(self.env)
        seed_order_templates(self.env)
        self.assertEqual(self.env.ref("sol_demo.demo_order_template_monthly_water"), template)
        self.assertEqual(template.name, "Customer-edited template")
        self.assertEqual(self.env.ref("sol_demo.demo_sale_order_from_template"), order)
        self.assertEqual(order._catalog_lines()[:1].product_uom_qty, 3)

    def test_upgrade_seeding_preserves_customized_salesperson_permissions(self):
        from odoo.addons.sol_demo.demo_order_templates import seed_order_templates

        for name in (
            "demo_sale_order_from_template",
            "demo_order_template_monthly_water",
            "demo_order_template_archived",
            "demo_sale_order_template_source",
        ):
            self.env.ref(f"sol_demo.{name}").unlink()
        person = self.env.ref("sol_demo.demo_person_sales")
        person.role_ids = False
        person.permission_ids = False
        seed_order_templates(self.env)
        self.assertFalse(person.role_ids)
        self.assertFalse(person.permission_ids)
        sales = self.env.ref("sol_demo.demo_res_users_sales")
        source = self.env.ref("sol_demo.demo_sale_order_template_source")
        order = self.env.ref("sol_demo.demo_sale_order_from_template")
        self.assertEqual(source.user_id, sales)
        self.assertEqual(order.user_id, sales)
        self.assertEqual((order.state, order.order_status, order.source), ("draft", "claimed", "sales"))

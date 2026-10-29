from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .template_case import TemplateCase


@tagged("post_install", "-at_install")
class TestOrderTemplateAccess(TemplateCase):
    def assert_hidden(self, template, user):
        records = self.env["medilab.order.template"].with_user(user)
        domain = [("id", "=", template.id)]
        self.assertFalse(records.search(domain))
        self.assertEqual(records.search_count(domain), 0)
        self.assertFalse(records.search_read(domain, ["name"]))
        self.assertFalse(records.name_search(template.sudo().name, domain=domain))
        for action in (
            lambda: template.with_user(user).read(["name"]),
            lambda: template.with_user(user).export_data(["name"]),
            lambda: template.with_user(user).write({"name": "Stolen"}),
            lambda: template.with_user(user).unlink(),
            lambda: template.with_user(user).action_archive(),
            lambda: template.with_user(user).action_create_order(),
        ):
            with self.assertRaises(AccessError):
                action()
        lines = template.sudo().line_ids
        line_domain = [("id", "in", lines.ids)]
        self.assertFalse(lines.with_user(user).search(line_domain))
        self.assertEqual(lines.with_user(user).search_count(line_domain), 0)
        self.assertFalse(lines.with_user(user).search_read(line_domain, ["quantity"]))
        self.assertFalse(lines.with_user(user).name_search(domain=line_domain))
        with self.assertRaises(AccessError):
            lines.with_user(user).export_data(["quantity"])
        with self.assertRaises(AccessError):
            lines.with_user(user).read(["quantity"])
        with self.assertRaises(AccessError):
            lines.with_user(user).write({"quantity": 3})
        with self.assertRaises(AccessError):
            lines.with_user(user).unlink()
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["medilab.order.template.line"].with_user(user).create(
                {
                    "template_id": template.id,
                    "product_id": self.lead_product.id,
                    "quantity": 1,
                }
            )

    def test_sales_isolation_reassignment_and_portal_denial(self):
        template = self.save_template()
        self.assert_hidden(template, self.other_sales)
        for action in (
            lambda: template.with_user(self.portal).search([]),
            lambda: template.with_user(self.portal).read(["name"]),
            lambda: template.with_user(self.portal).action_create_order(),
        ):
            with self.assertRaises(AccessError):
                action()
        self.assertEqual(template.with_user(self.head).name, "Monthly water check")
        self.assertEqual(template.with_user(self.env.ref("base.user_admin")).name, "Monthly water check")
        template.source_order_id.sudo().user_id = self.other_sales
        self.assert_hidden(template, self.sales)
        self.assertEqual(template.with_user(self.other_sales).name, "Monthly water check")
        result = template.with_user(self.other_sales).action_create_order()
        self.assertEqual(self.env["sale.order"].browse(result["res_id"]).user_id, self.other_sales)

    def test_unclaimed_queue_read_does_not_allow_template_operations(self):
        template = self.save_template()
        source = template.sudo().source_order_id
        source._set_status("submitted", {"user_id": False})
        self.assertTrue(source.with_user(self.sales).has_access("read"))
        self.assertTrue(source.with_user(self.other_sales).has_access("read"))
        self.assert_hidden(template, self.sales)
        self.assert_hidden(template, self.other_sales)
        for user in (self.sales, self.other_sales):
            with self.assertRaises(AccessError):
                source.with_user(user)._save_as_template("Queue selection")
        self.assertEqual(template.with_user(self.head).name, "Monthly water check")

    def test_extra_group_grant_does_not_bypass_global_restriction(self):
        template = self.save_template()
        for model in ("medilab.order.template", "medilab.order.template.line"):
            self.env["ir.access"].create(
                {
                    "name": "Extra grant",
                    "model_id": self.env["ir.model"]._get(model).id,
                    "group_id": self.env.ref("base.group_user").id,
                    "operation": "crud",
                    "domain": '[(1, "=", 1)]',
                }
            )
        self.assert_hidden(template, self.other_sales)

    def test_customer_and_source_are_immutable_including_direct_create(self):
        template = self.save_template()
        other_source = self.template_source()
        other_customer = self.env["medilab.customer"].create({"name": "Other customer"})
        for vals in ({"customer_id": other_customer.id}, {"source_order_id": other_source.id}):
            with self.assertRaises(AccessError):
                template.with_user(self.sales).write(vals)
        for user in (self.sales, self.other_sales):
            with self.assertRaises((AccessError, ValidationError)), self.cr.savepoint():
                self.env["medilab.order.template"].with_user(user).create(
                    {
                        "name": "Forged",
                        "customer_id": other_customer.id,
                        "source_order_id": template.source_order_id.id,
                    }
                )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["medilab.order.template"].with_user(self.other_sales).create(
                {
                    "name": "Forged",
                    "customer_id": self.customer_record.id,
                    "source_order_id": template.source_order_id.id,
                }
            )

    def test_source_customer_change_invalidates_without_blocking_source_edit(self):
        template = self.save_template()
        other_customer = self.env["medilab.customer"].create({"name": "Changed customer"})
        source = template.sudo().source_order_id
        source.write({"customer_id": other_customer.partner_id.id, "partner_id": other_customer.partner_id.id})
        self.assert_hidden(template, self.sales)
        self.assert_hidden(template, self.other_sales)
        before = self.env["sale.order"].search_count([])
        for user in (self.head, self.env.ref("base.user_admin")):
            records = self.env["medilab.order.template"].with_user(user)
            self.assertEqual(records.search([("id", "=", template.id)]), template.with_user(user))
            self.assertEqual(records.search_count([("id", "=", template.id)]), 1)
            self.assertEqual(
                records.search(
                    [
                        ("id", "=", template.id),
                        ("source_customer_matches", "=", False),
                    ]
                ),
                template.with_user(user),
            )
            self.assertEqual(records.search_read([("id", "=", template.id)], ["name"])[0]["name"], template.name)
            self.assertEqual(
                template.with_user(user).read(["customer_id"])[0]["customer_id"][0], self.customer_record.id
            )
            self.assertTrue(template.with_user(user).line_ids.read(["quantity"]))
            self.assertFalse(template.with_user(user).source_customer_matches)
            with self.assertRaises(ValidationError):
                template.with_user(user).action_create_order()
            with self.assertRaises(ValidationError):
                template.with_user(user)._create_order()
            with self.assertRaises(AccessError):
                template.with_user(user).write({"customer_id": other_customer.id})
            with self.assertRaises(AccessError):
                template.with_user(user).write({"source_order_id": source.id})
        with self.assertRaises(ValidationError):
            template.sudo()._create_order()
        self.assertEqual(self.env["sale.order"].search_count([]), before)
        source.write({"customer_id": self.customer.id, "partner_id": self.contact.id})
        self.assertTrue(template.with_user(self.sales).read(["name"]))

    def test_line_reparenting_requires_both_parents(self):
        mine = self.save_template()
        theirs = self.save_template()
        theirs.source_order_id.sudo().user_id = self.other_sales
        with self.assertRaises(AccessError):
            mine.line_ids.with_user(self.sales).write({"template_id": theirs.id})
        with self.assertRaises(AccessError):
            theirs.sudo().line_ids.with_user(self.sales).write({"template_id": mine.id})

    def test_completed_source_needs_read_access_only(self):
        source = self.template_source()
        source._set_status("completed")
        template = self.save_template(source)
        template.with_user(self.sales).write({"name": "Completed order selection"})
        self.assertEqual(self.reuse(template).state, "draft")
        with self.assertRaises(UserError), self.cr.savepoint():
            source.unlink()

    def test_permissions_are_required_even_with_source_access(self):
        template = self.save_template()
        self.sales_person.role_ids = False
        self.sales_person.permission_ids = self.sales_person.permission_ids.filtered(
            lambda permission: not permission.document_model.startswith("medilab.order.template")
        )
        with self.assertRaises(AccessError):
            template.with_user(self.sales).read(["name"])
        with self.assertRaises(AccessError):
            template.source_order_id.with_user(self.sales)._save_as_template("No permission")

    def test_completed_source_can_be_used_without_source_edit_permission(self):
        source = self.template_source()
        source._set_status("completed")
        self.sales_person.role_ids = False
        self.sales_person.permission_ids = self.sales_person.permission_ids.filtered(
            lambda permission: permission.code != "order.edit.all"
        )
        self.assertFalse(source.with_user(self.sales).has_access("write"))
        template = self.save_template(source)
        template.with_user(self.sales).write({"name": "Read-only source"})
        self.assertTrue(template.with_user(self.sales).read(["name"]))

    def test_customer_merge_keeps_source_template_and_lines_consistent(self):
        duplicate = self.env["medilab.customer"].create(
            {"name": "Duplicate customer", "duplicate_of_id": self.customer_record.id}
        )
        source = self.template_source(customer_id=duplicate.partner_id.id, partner_id=duplicate.partner_id.id)
        template = self.save_template(source)
        lines = template.line_ids
        duplicate.action_merge_duplicate()
        self.assertEqual(template.customer_id, self.customer_record)
        self.assertEqual(template.line_ids, lines)
        self.assertTrue(template.with_user(self.sales).source_customer_matches)
        self.assertEqual(self.reuse(template).customer_id, self.customer)

    def test_create_only_can_save_initial_lines_but_cannot_add_or_reparent_later(self):
        source = self.template_source()
        self.sales_person.role_ids = False
        self.sales_person.permission_ids = self.sales_person.permission_ids.filtered(
            lambda permission: (
                not permission.document_model.startswith("medilab.order.template")
                or permission.action in ("read", "create")
            )
        )
        template = self.save_template(source)
        self.assertEqual(template.line_ids.mapped("quantity"), [2, 3])
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["medilab.order.template.line"].with_user(self.sales).with_context(
                creating_template_ids=template.ids
            ).create({"template_id": template.id, "product_id": self.lead_product.id, "quantity": 2})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["medilab.order.template"].with_user(self.sales).create(
                {
                    "name": "Linked selection",
                    "source_order_id": source.id,
                    "customer_id": self.customer_record.id,
                    "line_ids": [Command.link(template.line_ids[0].id)],
                }
            )

    def test_privileged_recovery_archives_deletes_and_preserves_audit_history(self):
        customer = self.env["medilab.customer"].create({"name": "Recovery customer"})
        for user in (self.head, self.env.ref("base.user_admin")):
            with self.subTest(user=user.login):
                template = self.save_template()
                source = template.sudo().source_order_id
                source.write({"customer_id": customer.partner_id.id, "partner_id": customer.partner_id.id})
                with self.assertRaises(UserError):
                    source.with_user(user).unlink()
                template.with_user(user).action_archive()
                self.assertFalse(template.with_user(user).active)
                self.assertTrue(template.with_user(user).read(["name"]))
                with self.assertRaises(ValidationError):
                    template.with_user(user).action_create_order()
                entries = self.env["medilab.audit.entry"].search(
                    [
                        ("document_model", "=", "medilab.order.template"),
                        ("document_id", "=", template.id),
                    ]
                )
                self.assertIn("archive", entries.mapped("action"))
                lines = template.with_user(user).line_ids
                template.with_user(user).unlink()
                self.assertFalse(template.exists())
                self.assertFalse(lines.exists())
                self.assertEqual(entries.exists(), entries)
                self.assertTrue(
                    self.env["medilab.audit.entry"].search(
                        [
                            ("document_model", "=", "medilab.order.template"),
                            ("document_id", "=", template.id),
                            ("action", "=", "delete"),
                        ]
                    )
                )
                source.with_user(user).unlink()
                self.assertFalse(source.exists())

    def test_privileged_recovery_still_requires_source_order_read_access(self):
        template = self.save_template()
        source = template.sudo().source_order_id
        customer = self.env["medilab.customer"].create({"name": "Restricted recovery customer"})
        source.write({"customer_id": customer.partner_id.id, "partner_id": customer.partner_id.id})
        self.env["ir.access"].create(
            {
                "name": "Restrict this source even for managers",
                "model_id": self.env["ir.model"]._get("sale.order").id,
                "operation": "r",
                "domain": repr([("id", "!=", source.id)]),
            }
        )
        for user in (self.head, self.env.ref("base.user_admin")):
            self.assertFalse(source.with_user(user).has_access("read"))
            self.assert_hidden(template, user)

    def test_mismatch_reuse_does_not_trust_a_caller_supplied_computed_flag(self):
        template = self.save_template()
        source = template.sudo().source_order_id
        customer = self.env["medilab.customer"].create({"name": "Changed source customer"})
        source.write({"customer_id": customer.partner_id.id, "partner_id": customer.partner_id.id})
        before = self.env["sale.order"].search_count([])
        for record in (
            template.with_user(self.head),
            template.with_user(self.env.ref("base.user_admin")),
            template.sudo(),
        ):
            with self.subTest(user=record.env.user.login, sudo=record.env.su):
                record.write({"source_customer_matches": True})
                with self.assertRaises(ValidationError):
                    record._create_order()
        self.assertEqual(self.env["sale.order"].search_count([]), before)

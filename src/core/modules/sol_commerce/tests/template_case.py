from .order_case import OrderCase


class TemplateCase(OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer_record.default_contact_id = cls.contact
        for user in (cls.sales, cls.other_sales, cls.head, cls.portal):
            user.group_ids |= cls.env.ref("base.group_allow_export")
        permissions = cls.env["medilab.permission"].search(
            [
                ("document_model", "in", ["medilab.order.template", "medilab.order.template.line"]),
            ]
        )
        for person in (cls.sales_person, cls.other_person, cls.head_person):
            person.permission_ids |= permissions

    def template_source(self, lines=None, **vals):
        return self.make_order(
            lines or [(self.lead_product, 1.5), (self.package_product, 2.25)],
            status="claimed",
            user_id=self.sales.id,
            **vals,
        )

    def save_template(self, source=None):
        return (
            (source if source is not None else self.template_source())
            .with_user(self.sales)
            ._save_as_template("Monthly water check")
        )

    def reuse(self, template):
        action = template.with_user(self.sales).action_create_order()
        return self.env["sale.order"].browse(action["res_id"])

import base64

from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER
from odoo.addons.sol_laboratory.services.record_id import persisted_id

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


@tagged("post_install", "-at_install")
class TestCustomerProfile(RequestCase):
    """Sales maintain customer profiles; a business keeps its own people and logo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(
            cls.env,
            login="customer.editor",
            groups="base.group_user,sol_laboratory.group_permission_customer_read_all,"
            "sol_laboratory.group_permission_customer_create_all,sol_laboratory.group_permission_customer_edit_all",
        )
        cls.reader = new_test_user(
            cls.env, login="customer.reader", groups="base.group_user,sol_laboratory.group_permission_customer_read_all"
        )
        cls.hoa = cls.env["res.partner"].create({"name": "Tran Thi Hoa", "parent_id": cls.customer.partner_id.id})

    def test_sales_edit_the_profile_and_people_without_contact_rights(self):
        customer = self.customer.with_user(self.editor)

        customer.write(
            {
                "phone": "028 3750 1234",
                "child_ids": [
                    Command.update(persisted_id(self.hoa), {"function": "Quality manager"}),
                    Command.create({"name": "Le Van Nam", "function": "Buyer", "type": "contact"}),
                ],
            }
        )

        self.assertEqual(self.customer.phone, "028 3750 1234")
        self.assertEqual(self.hoa.function, "Quality manager")
        self.assertIn("Le Van Nam", self.customer._contacts().mapped("name"))
        with self.assertRaises(AccessError):
            customer.write({"child_ids": [Command.link(persisted_id(self.env.ref("base.partner_admin")))]})

    def test_the_citizen_id_is_read_only_by_those_who_maintain_customers(self):
        self.customer.citizen_id = "079085001234"
        self.env.invalidate_all()

        self.assertEqual(self.customer.with_user(self.editor).citizen_id, "079085001234")
        with self.assertRaises(AccessError):
            self.customer.with_user(self.reader).read(["citizen_id"])

    def test_only_those_who_maintain_customers_see_the_actions_and_the_citizen_id(self):
        def form(user):
            return self.env[MODEL_CUSTOMER].with_user(user).get_view(view_type="form")["arch"]

        for user, shown in ((self.editor, True), (self.reader, False)):
            arch = form(user)
            for node in ('name="action_merge_duplicate"', 'name="action_invite_to_portal"', 'name="citizen_id"'):
                with self.subTest(user=user.login, node=node):
                    self.assertEqual(node in arch, shown)

    def test_a_citizen_id_already_given_is_not_asked_again(self):
        customer = self.env[MODEL_CUSTOMER].create({"name": "Pham Van Long"}).sudo()

        customer.set_citizen_id(" 079085001234 ")

        self.assertEqual(customer.citizen_id, "079085001234")
        with self.assertRaises(UserError):
            customer.set_citizen_id("079085009999")

    def test_people_are_changed_only_through_their_contact_details(self):
        customer = self.customer.with_user(self.editor)
        admin = self.env.ref("base.user_admin")
        probe = {
            "login": "probe.admin",
            "name": "Probe",
            "group_ids": [Command.link(persisted_id(self.env.ref("base.group_system")))],
        }

        for command in (
            Command.create({"name": "Probe", "user_ids": [Command.create(probe)]}),
            Command.update(persisted_id(self.hoa), {"user_ids": [Command.link(persisted_id(admin))]}),
            Command.update(
                persisted_id(self.hoa), {"child_ids": [Command.link(persisted_id(self.env.ref("base.partner_admin")))]}
            ),
        ):
            with self.subTest(command=command), self.assertRaises(AccessError):
                customer.write({"child_ids": [command]})

        self.assertFalse(self.env["res.users"].search([("login", "=", "probe.admin")]))
        self.assertEqual(admin.partner_id, self.env.ref("base.partner_admin"))
        self.assertFalse(self.env.ref("base.partner_admin").parent_id)

    def test_a_business_is_not_given_a_citizen_id(self):
        customer = self.customer.sudo()
        customer.vat = "0301234567"

        with self.assertRaises(UserError):
            customer.set_citizen_id("079085001234")

        self.assertFalse(customer.citizen_id)
        self.assertTrue(customer.is_company)

    def test_a_business_adds_edits_removes_and_picks_its_default_contact(self):
        customer = self.customer.sudo()

        lan = customer.save_contact({"name": " Ngo Thi Lan ", "function": "Accountant", "email": "lan@anphu.example"})
        customer.save_contact({"name": "Ngo Thi Lan", "phone": "0909 777 888"}, lan)
        customer.set_default_contact(lan)

        self.assertEqual((lan.name, lan.phone, lan.parent_id), ("Ngo Thi Lan", "0909 777 888", customer.partner_id))
        self.assertEqual(customer.default_contact_id, lan)

        customer.remove_contact(lan)

        self.assertFalse(lan.active)
        self.assertFalse(customer.default_contact_id)
        self.assertNotIn(lan, customer._contacts())
        with self.assertRaises(UserError):
            customer.save_contact({"name": " "})

    def test_another_customers_person_cannot_be_changed(self):
        other = self.env[MODEL_CUSTOMER].create({"name": "Green Farm JSC"})
        stranger = self.env["res.partner"].create({"name": "Vo Van Tam", "parent_id": other.partner_id.id})

        for action in (
            lambda: self.customer.sudo().save_contact({"name": "Vo Van Tam"}, stranger),
            lambda: self.customer.sudo().remove_contact(stranger),
            lambda: self.customer.sudo().set_default_contact(stranger),
        ):
            with self.assertRaises(AccessError):
                action()

    def test_a_logo_is_a_png_or_jpeg_of_at_most_2_mb(self):
        customer = self.customer.with_user(self.editor)

        customer.write({"image_1920": base64.b64encode(PNG).decode()})
        self.assertTrue(self.customer.image_128)

        for image in (GIF, PNG + b"0" * (2 * 1024 * 1024)):
            with self.assertRaises(UserError):
                customer.write({"image_1920": base64.b64encode(image).decode()})

        customer.write({"image_1920": False})
        self.assertFalse(self.customer.image_128)

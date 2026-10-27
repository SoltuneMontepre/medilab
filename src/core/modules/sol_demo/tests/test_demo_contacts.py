from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_NOTIFICATION_CONTACT, MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER


@tagged("post_install", "-at_install")
class TestDemoContacts(TransactionCase):
    def customer(self, xml_id):
        return self.env.ref(f"sol_demo.{xml_id}")

    def test_a_business_has_several_complete_contacts_and_a_default(self):
        customer = self.customer("demo_customer_nuoc_sach")
        contacts = customer._contacts()

        self.assertGreater(len(contacts), 1)
        for contact in contacts:
            with self.subTest(contact=contact.name):
                self.assertTrue(contact.function and contact.email and contact.phone)
        self.assertIn(customer.default_contact_id, contacts)

    def test_a_business_has_contacts_but_no_default(self):
        customer = self.customer("demo_customer_an_phu")

        self.assertTrue(customer._contacts())
        self.assertFalse(customer.default_contact_id)

    def test_orders_of_one_business_name_different_contacts(self):
        business = self.env.ref("sol_demo.demo_res_partner_nuoc_sach")
        orders = self.env[MODEL_SALE_ORDER].search([("customer_id", "=", business.id)])

        self.assertGreater(len(orders.partner_id), 1)

    def test_an_order_keeps_a_contact_the_business_removed(self):
        former = self.env.ref("sol_demo.demo_res_partner_thao")
        order = self.env[MODEL_SALE_ORDER].search([("partner_id", "=", former.id)])

        self.assertFalse(former.active)
        self.assertTrue(order)
        self.assertNotIn(former, self.customer("demo_customer_nuoc_sach")._contacts())

    def test_a_business_sends_an_event_to_a_contact_other_than_the_orders(self):
        route = self.env[MODEL_NOTIFICATION_CONTACT].search(
            [("partner_id", "=", self.env.ref("sol_demo.demo_res_partner_nuoc_sach").id)], limit=1
        )
        orders = self.env[MODEL_SALE_ORDER].search([("customer_id", "=", route.partner_id.id)])

        self.assertTrue(orders.filtered(lambda order: order.partner_id != route.contact_id))

    def test_an_individual_is_their_own_contact(self):
        person = self.env.ref("sol_demo.demo_res_partner_minh")
        order = self.env[MODEL_SALE_ORDER].search([("customer_id", "=", person.id)])

        self.assertTrue(order)
        self.assertEqual(order.partner_id, person)
        self.assertFalse(self.env[MODEL_CUSTOMER].search([("partner_id", "=", person.id)])._contacts())

    def test_vietnamese_businesses_and_their_contacts_use_vietnamese(self):
        # A contact who signs in keeps the language of the screens the browser tests read.
        for xml_id in ("demo_customer_nuoc_sach", "demo_customer_an_phu", "demo_customer_green_farm"):
            customer = self.customer(xml_id)
            for partner in customer.partner_id | customer._contacts().filtered(lambda contact: not contact.user_ids):
                with self.subTest(partner=partner.name):
                    self.assertEqual(partner.lang, "vi_VN")

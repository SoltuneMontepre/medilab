"""Uninstalling E-commerce leaves each test request its order's number as text (SH-01).

``task test:uninstall`` runs this standalone function before the Laboratory one, while E-commerce is still installed.
"""

from odoo.tests.common import standalone

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.xml_ids import MODULE
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.tests.test_uninstall import uninstall_keeping_laboratory_data


@standalone("medilab_commerce_uninstall")
def test_uninstalling_keeps_the_order_number_on_test_requests(env):
    partner = env["res.partner"].create({"name": "Cong ty Nuoc Sach", "is_company": True})
    customer = env[MODEL_CUSTOMER].create({"partner_id": partner.id})
    request = env[MODEL_TEST_REQUEST].create({"customer_id": customer.id})
    order = env[MODEL_SALE_ORDER].create({"partner_id": partner.id, "test_request_id": request.id})
    number = order.name
    env.cr.commit()

    env = uninstall_keeping_laboratory_data(env, MODULE)

    assert env[MODEL_TEST_REQUEST].browse(request.id).order_number == number, "the test request lost its order number"

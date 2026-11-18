from datetime import timedelta

from odoo import fields

from .demo_dispatches import SURFACE_WATER, _received_tests
from .demo_orders import _xml_id
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SUBCONTRACTOR

FAILED_SAMPLE = ("Nước sông Đồng Nai trạm bơm Hóa An",)
FAILED_REASON = "Xe giao mẫu hỏng giữa đường, thùng bảo quản mất lạnh; mẫu được mang về phòng thí nghiệm."
LAPSED_SAMPLE = ("Nước kênh Nhiêu Lộc cầu Thị Nghè",)
TURNAROUNDS = {"demo_parameter_method_lead_subcontracted": 6, "demo_parameter_method_chlorpyrifos_ug": 9}


def seed_dispatch_delivery(env):
    """The turnaround of the subcontracted ways, a sent lead dispatch to Northern whose delivery failed, and a draft
    dispatch to Saigon Analytical Laboratory, whose accreditation lapsed after the head put a lead test in it."""
    if env.ref("sol_demo.demo_subcontract_dispatch_failed_delivery", raise_if_not_found=False):
        return
    for xml_id, days in TURNAROUNDS.items():
        way = env.ref(f"sol_demo.{xml_id}")
        if not way.turnaround_days:
            way.turnaround_days = days
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    courier = env.ref("sol_demo.demo_person_sample_delivery_staff")
    northern = env.ref("sol_demo.demo_parameter_method_lead_subcontracted")
    today = fields.Date.today()

    failed = _received_tests(env, "nuoc_sach", SURFACE_WATER, "lead", FAILED_SAMPLE, "2 bottles")
    dispatch = failed.with_user(head)._accept_outsourcing(northern)
    dispatch.write({"courier_id": courier.id})
    dispatch.with_user(head).action_send()
    dispatch.with_user(head)._report_failed_delivery(FAILED_REASON)
    _xml_id(env, "demo_subcontract_dispatch_failed_delivery", dispatch)

    company = env["res.partner"].create(
        {"name": "Saigon Analytical Laboratory", "is_company": True, "city": "Hồ Chí Minh", "phone": "028 3822 4455"}
    )
    contact = env["res.partner"].create({"name": "Trần Văn Khoa", "parent_id": company.id, "function": "QA Manager"})
    saigon = env[MODEL_SUBCONTRACTOR].create(
        {
            "partner_id": company.id,
            "contact_person_id": contact.id,
            "accreditation_number": "VILAS 505",
            "accreditation_expiry": today + timedelta(days=30),
            "contract_reference": "HD-2025/03",
        }
    )
    way = env[MODEL_PARAMETER_METHOD].create(
        {
            "parameter_id": northern.parameter_id.id,
            "method_id": northern.method_id.id,
            "subcontractor_id": saigon.id,
            "turnaround_days": 5,
        }
    )
    env.ref("sol_demo.demo_parameter_method_sample_type_lead_subcontracted_surface_water").copy(
        {"parameter_method_id": way.id, "is_default": False}
    )
    lapsed = _received_tests(env, "nuoc_sach", SURFACE_WATER, "lead", LAPSED_SAMPLE, "2 bottles")
    draft = lapsed.with_user(head)._accept_outsourcing(way)
    saigon.accreditation_expiry = today - timedelta(days=1)
    _xml_id(env, "demo_subcontractor_saigon_analytical", saigon)
    _xml_id(env, "demo_parameter_method_lead_saigon", way)
    _xml_id(env, "demo_subcontract_dispatch_accreditation_lapsed", draft)

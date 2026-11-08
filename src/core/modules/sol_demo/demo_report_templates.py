import logging
from unittest.mock import patch

from odoo import fields

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_ACTIONS_REPORT,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_REPORT_TEMPLATE,
    MODEL_TEST_REPORT_CANDIDATE,
)
from odoo.addons.sol_laboratory.constants.report_templates import AVAILABLE
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT
from odoo.addons.sol_laboratory.services import laboratory_bucket

_logger = logging.getLogger(__name__)

# The demo templates: their name, language and how many versions each has; all but the last version are archived and
# the last is available, and the templates named in DRAFTS also have a draft version after it.
TEMPLATES = (
    ("bilingual", "Phiếu kết quả nước uống song ngữ", "bilingual", 2),
    ("vietnamese", "Phiếu kết quả thử nghiệm", "vi", 1),
    ("english", "Test report", "en", 1),
)
DRAFTS = ("bilingual",)


def seed_report_templates(env):
    """A bilingual template with an archived first version, an available second one and a draft third one, Vietnamese
    and English templates with an available version each, and the draft report of Nước Uống Sạch prepared as a PDF
    waiting for the lab head's review."""
    if env.ref("sol_demo.demo_report_template_bilingual", raise_if_not_found=False):
        return
    if not laboratory_bucket.is_ready():
        _logger.warning("The laboratory files bucket does not answer: the demo report templates are not seeded.")
        return
    administrator = env.ref("sol_demo.demo_res_users_administrator")
    xml_ids = []
    for key, name, language, count in TEMPLATES:
        template = env[MODEL_REPORT_TEMPLATE].with_user(administrator).create({"name": name, "language": language})
        xml_ids.append((f"demo_report_template_{key}", template))
        for number in range(1, count + 1):
            version = template.version_ids.filtered(lambda version, number=number: version.number == number)
            # ONLYOFFICE does not run while the demo installs, so the versions are made available without a preview.
            version.sudo().write(
                {
                    "state": AVAILABLE,
                    "docx_version_id": template.file_id.current_version_id.id,
                    "made_available_at": fields.Datetime.now(),
                }
            )
            xml_ids.append((f"demo_report_template_version_{key}_{number}", version))
            if number < count or key in DRAFTS:
                version.with_user(administrator).action_new_draft()
            if number < count:
                version.with_user(administrator).action_archive()
        if key in DRAFTS:
            xml_ids.append((f"demo_report_template_version_{key}_{count + 1}", template._draft_version()))

    report = env.ref("sol_demo.demo_test_report_draft")
    staff = env.ref("sol_demo.demo_res_users_sample_delivery_staff")
    # The PDF ONLYOFFICE would convert is stood in for by the report's print, as ONLYOFFICE does not run while the demo
    # installs.
    pdf, _type = env[MODEL_IR_ACTIONS_REPORT]._render_qweb_pdf(TEST_REPORT_REPORT, report.ids)
    sessions = type(env[MODEL_LABORATORY_EDITING_SESSION])
    with (
        patch.object(sessions, "_check_editing_available", lambda self: None),
        patch.object(type(env[MODEL_TEST_REPORT_CANDIDATE]), "_convert", lambda self, content, title: pdf),
    ):
        candidate = report.with_user(staff)._prepare_candidate()
    xml_ids.append(("demo_test_report_candidate_draft", candidate))

    env["ir.model.data"]._update_xmlids(
        [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in xml_ids]
    )

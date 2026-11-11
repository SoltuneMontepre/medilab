import hashlib
from ast import literal_eval
from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import new_test_user

from .editing_service import use_editing_service
from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_ACTIONS_ACT_WINDOW,
    MODEL_REPORT_TEMPLATE,
    MODEL_TEST_REPORT,
)
from odoo.addons.sol_laboratory.constants.report_templates import AVAILABLE
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

# The PDF ONLYOFFICE answers with in tests.
PDF = b"%PDF-1.7\n% prepared report\n"
# Where the conversion is asked for.
CONVERSION = "odoo.addons.sol_laboratory.models.testing.test_report_candidate.convert_to_pdf"
TEMPLATE_PERMISSIONS = (
    "report_template.read.all",
    "report_template.create.all",
    "report_template.edit.all",
    "report_template_version.read.all",
    "report_template_version.create.all",
    "report_template_version.edit.all",
    "report_template_version.archive.all",
)


class MemoryBucket:
    """The laboratory files bucket as the tests see it: objects kept in memory, addresses that are never fetched."""

    def __init__(self, case):
        self.objects = {}
        for name in ("write", "read", "read_address"):
            case.enterContext(patch.object(laboratory_bucket, name, getattr(self, f"_{name}")))

    def _write(self, key, chunks):
        data = b"".join(chunks)
        self.objects[key] = data
        return len(data), hashlib.sha256(data).hexdigest()

    @contextmanager
    def _read(self, key):
        if key not in self.objects:
            raise laboratory_bucket.BucketUnavailable(key)
        yield iter([self.objects[key]])

    def _read_address(self, key, seconds, filename):
        return f"https://bucket.lab.example/{key}"


class ReportCase(ResultCase):
    """The lab head signs the report of the lead request once its results are approved and its PDF is prepared, from a
    template an administrator of templates made available, by a sample delivery staff member who edits reports and
    delivers them. The bucket is in memory and ONLYOFFICE is up and converting."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        chain = cls.approval_chain(MODEL_TEST_REPORT, (("Lab head", "qa_lab_head", False, True),))
        cls.lab_head = cls.create_person(
            "Vo Thi Giang",
            login="giang.vo",
            permissions=(
                "test_report.read.all",
                "test_report.sign.all",
                "test_report_candidate.read.all",
                "test_request.read.all",
                "test_result.read.all",
            ),
            roles=chain.level_ids.role_id,
        )
        cls.courier = cls.create_person(
            "Dang Van Hai",
            login="hai.dang",
            permissions=(
                "test_report.read.all",
                "test_report.edit.all",
                "test_request.read.all",
                "report_template_version.read.all",
                "test_report_candidate.read.all",
            ),
        )
        cls.template_admin = cls.create_person("Ly Thi Mai", login="mai.ly", permissions=TEMPLATE_PERMISSIONS)

    def setUp(self):
        super().setUp()
        self.bucket = MemoryBucket(self)
        self.health_check = use_editing_service(self)
        self.conversion = self.enterContext(patch(CONVERSION, return_value=PDF))
        # The available template made for each report language.
        self.templates = {}

    @classmethod
    def portal_user(cls):
        """The portal user of a contact of the customer, who downloads its issued reports."""
        contact = cls.env["res.partner"].create({"name": "Nguyen Thi Hoa", "parent_id": cls.customer.partner_id.id})
        return new_test_user(cls.env, "hoa.portal", groups="base.group_portal", partner_id=contact.id)

    def new_template(self, language="bilingual", name="Water report"):
        return self.as_person(self.env[MODEL_REPORT_TEMPLATE], self.template_admin).create(
            {"name": name, "language": language}
        )

    def available_template(self, language="bilingual", name="Water report"):
        template = self.new_template(language, name)
        version = self.as_person(template.version_ids, self.template_admin)
        version.action_preview()
        version.action_make_available()
        self.templates.setdefault(language, template)
        return template

    def complete(self, test=None, **values):
        """Enter, send and approve the reported result of the test."""
        result = self.enter(test=test, **values)
        self.send(result)
        self.approve(result)
        return result

    def report(self):
        return self.env[MODEL_TEST_REPORT].search([("request_id", "=", self.request.id)])

    def editor(self, report=None):
        return self.as_person(report or self.report(), self.courier)

    def prepare(self, report=None):
        """Prepare the report's PDF for review as its editor, from an available template of its language, and return
        it."""
        report = (report or self.report()).sudo()
        if not report.template_version_id:
            template = self.templates.get(report.language or "") or self.available_template(report.language or "")
            report.template_version_id = template.version_ids.filtered(lambda version: version.state == AVAILABLE)
        self.editor(report).action_prepare_pdf()
        return report._candidate()

    def sign(self, document=None):
        """Sign the document as the lab head; a report first gets its PDF prepared when none waits for review."""
        document = document or self.report()
        if document._name == MODEL_TEST_REPORT and not document.sudo()._candidate():
            self.prepare(document)
        self.as_person(document, self.lab_head).action_sign()

    def waiting_for(self, action):
        """The reports an action of the Laboratory menu lists."""
        domain = reference_as(
            self.env[MODEL_IR_ACTIONS_ACT_WINDOW], f"sol_laboratory.action_medilab_test_report_{action}"
        ).domain
        return self.env[MODEL_TEST_REPORT].search(literal_eval(assert_instance(domain, str)))

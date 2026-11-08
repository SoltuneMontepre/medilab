import hashlib
import io
import zipfile
from contextlib import contextmanager
from unittest.mock import patch

from .editing_service import use_editing_service
from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_REPORT_TEMPLATE
from odoo.addons.sol_laboratory.services import laboratory_bucket

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


class ReportPreparationCase(ReportCase):
    """The completed lead request, whose draft report the courier edits and prepares from the available bilingual
    template an administrator of templates made, with the bucket in memory and ONLYOFFICE up and converting."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_admin = cls.create_person("Ly Thi Mai", login="mai.ly", permissions=TEMPLATE_PERMISSIONS)
        cls.grant(cls.courier, "report_template_version.read.all", "test_report_candidate.read.all")

    def setUp(self):
        super().setUp()
        self.bucket = MemoryBucket(self)
        self.health_check = use_editing_service(self)
        self.conversion = self.enterContext(patch(CONVERSION, return_value=PDF))
        self.template = self.available_template()
        self.complete()

    def new_template(self, language="bilingual", name="Water report"):
        return self.as_person(self.env[MODEL_REPORT_TEMPLATE], self.template_admin).create(
            {"name": name, "language": language}
        )

    def available_template(self, language="bilingual", name="Water report"):
        template = self.new_template(language, name)
        version = self.as_person(template.version_ids, self.template_admin)
        version.action_preview()
        version.action_make_available()
        return template

    def docx_of(self, version):
        return self.bucket.objects[version.sudo().content_id.object_key]

    @staticmethod
    def rewrite(docx, old, new):
        """The DOCX with old replaced by new in its body, as an editor changing it would save it."""
        source, buffer = zipfile.ZipFile(io.BytesIO(docx)), io.BytesIO()
        with source, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                data = source.read(info)
                target.writestr(info, data.replace(old, new) if info.filename == "word/document.xml" else data)
        return buffer.getvalue()

    def save_docx(self, file, data, user):
        """Store the bytes as a save of the editor, as the editing service's callback does."""
        content = self.env["medilab.laboratory.content"]._store_bytes(data)
        return file.sudo()._add_version(content=content, source="edited_online", user=user)

    def editor(self, report=None):
        return self.as_person(report or self.report(), self.courier)

import io
import zipfile

from .report_case import ReportCase


class ReportPreparationCase(ReportCase):
    """The completed lead request, whose draft report the courier edits and prepares from the available bilingual
    template an administrator of templates made."""

    def setUp(self):
        super().setUp()
        self.template = self.available_template()
        self.complete()

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

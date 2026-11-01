import logging
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from odoo import api, models
from odoo.tools import config

from odoo.addons.sol_laboratory.constants.laboratory_bucket import (
    FILESTORE_GC_GRACE,
    FILESTORE_PREFIX,
    READ_CHUNK_SIZE,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.services import laboratory_bucket, module_files

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_attachment as IrAttachmentBase
else:
    IrAttachmentBase = object

STORED_FILE = re.compile(r"[0-9a-f]{2}/[0-9a-f]+")

_logger = logging.getLogger(__name__)


# Tệp Đính Kèm
class IrAttachment(models.Model, IrAttachmentBase):
    _inherit = MODEL_IR_ATTACHMENT

    @api.model
    def _bucket_key(self, fname):
        return f"{FILESTORE_PREFIX}/{self.env.cr.dbname}/{fname}"

    @api.model
    def _file_write(self, fname, bin_value):
        result = super()._file_write(fname, bin_value)
        if laboratory_bucket.filestore_enabled():
            self._upload_file(fname)
        return result

    def _file_read(self):
        if self.store_fname and laboratory_bucket.filestore_enabled():
            self._download_file(self.store_fname)
        return super()._file_read()

    def _to_http_stream(self):
        if self.store_fname and laboratory_bucket.filestore_enabled():
            self._download_file(self.store_fname)
        return super()._to_http_stream()

    def _register_hook(self):
        super()._register_hook()
        if not (config["init"] or config["update"]):
            return
        self._restore_module_files()
        if laboratory_bucket.filestore_enabled():
            for fname in self._local_files():
                self._upload_file(fname)

    @api.autovacuum
    def _gc_filestore_bucket(self):
        if not laboratory_bucket.filestore_enabled():
            return
        prefix = self._bucket_key("")
        kept = set(
            self.sudo()
            .with_context(active_test=False)
            .search_fetch(
                [("store_fname", "!=", False), "|", ("res_field", "=", False), ("res_field", "!=", False)],
                ["store_fname"],
            )
            .mapped("store_fname")
        )
        limit = datetime.now(UTC) - timedelta(seconds=FILESTORE_GC_GRACE)
        for key, modified in list(laboratory_bucket.keys(prefix)):
            if key.removeprefix(prefix) not in kept and modified < limit:
                laboratory_bucket.delete(key)

    @api.model
    def _move_mounted_files(self):
        """Move the files the bucket held when it was mounted as the filestore, at `<database>/<store_fname>`, to their
        key under the filestore prefix. The object is read and written again, as server-side copies are limited."""
        if not laboratory_bucket.filestore_enabled():
            return
        prefix = f"{self.env.cr.dbname}/"
        for key, _modified in list(laboratory_bucket.keys(prefix)):
            fname = key.removeprefix(prefix)
            if not STORED_FILE.fullmatch(fname):
                continue
            target = self._bucket_key(fname)
            if laboratory_bucket.object_size(target) is None:
                with laboratory_bucket.read(key) as chunks:
                    laboratory_bucket.write(target, chunks)
            laboratory_bucket.delete(key)

    @api.model
    def _restore_module_files(self):
        """Write the files that are in neither the local filestore nor the bucket again from an installed module's
        file with the same content, such as images module data loads once, then compute again the images stored from
        them. A file no module holds, such as an uploaded logo, stays missing."""
        missing = self._missing_files()
        if not missing:
            return
        modules = self.env["ir.module.module"].sudo().search([("state", "=", "installed")]).mapped("name")
        sources = module_files.by_checksum(
            modules, {(attachment.file_size, attachment.checksum) for attachment in missing}
        )
        restored = missing.browse()
        for attachment in missing:
            source = sources.get(attachment.checksum)
            if source:
                with open(source, "rb") as file:
                    self._file_write(attachment.store_fname, file)
                restored |= attachment
        self._compute_stored_images(missing - restored)
        lost = missing.filtered(lambda attachment: not os.path.exists(self._full_path(attachment.store_fname)))
        _logger.info("Wrote %s attachment files again from the installed modules.", len(missing) - len(lost))
        if lost:
            _logger.warning(
                "%s attachment files are in neither the local filestore, the bucket nor an installed module: %s",
                len(lost),
                ", ".join(sorted({attachment.store_fname for attachment in lost if attachment.store_fname})),
            )

    @api.model
    def _missing_files(self):
        attachments = (
            self.sudo()
            .with_context(active_test=False)
            .search_fetch(
                [("store_fname", "!=", False), "|", ("res_field", "=", False), ("res_field", "!=", False)],
                ["store_fname", "checksum", "file_size", "res_model", "res_id", "res_field"],
            )
        )
        in_bucket = set()
        if laboratory_bucket.filestore_enabled():
            prefix = self._bucket_key("")
            in_bucket = {key.removeprefix(prefix) for key, _modified in laboratory_bucket.keys(prefix)}
        return attachments.filtered(
            lambda attachment: (
                attachment.store_fname not in in_bucket and not os.path.exists(self._full_path(attachment.store_fname))
            )
        )

    @api.model
    def _compute_stored_images(self, unrestored):
        """Compute again the stored computed binary fields, such as resized images and the company's web logo, of the
        records whose files are missing, except a record whose own file could not be written again, whose images
        would be computed empty."""
        records = {}
        for attachment in unrestored:
            if attachment.res_model not in self.env or not attachment.res_field:
                continue
            records.setdefault(attachment.res_model, {}).setdefault(attachment.res_id, []).append(attachment.res_field)
        for model_name, fields_by_id in records.items():
            model = self.env[model_name].sudo().with_context(active_test=False)
            computed = [
                field
                for field in model._fields.values()
                if field.type in ("binary", "image") and field.store and field.compute
            ]
            ids = [
                res_id
                for res_id, names in fields_by_id.items()
                if all(name in model._fields and model._fields[name] in computed for name in names)
            ]
            targets = model.browse(ids).exists()
            for field in computed:
                self.env.add_to_compute(field, targets)
        self.env.flush_all()

    @api.model
    def _upload_file(self, fname):
        key = self._bucket_key(fname)
        if laboratory_bucket.object_size(key) is not None:
            return
        with open(self._full_path(fname), "rb") as file:
            laboratory_bucket.write(key, iter(lambda: file.read(READ_CHUNK_SIZE), b""))

    @api.model
    def _download_file(self, fname):
        path = self._full_path(fname)
        if os.path.exists(path):
            return
        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as file:
            try:
                found = laboratory_bucket.save(self._bucket_key(fname), file)
            except BaseException:
                os.unlink(file.name)
                raise
        if found:
            os.chmod(file.name, 0o444)
            os.replace(file.name, path)
        else:
            os.unlink(file.name)
            _logger.warning("Attachment file %s is in neither the local filestore nor the bucket.", fname)

    @api.model
    def _local_files(self):
        root = self._filestore()
        for folder, _folders, names in os.walk(root):
            for name in names:
                fname = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                if STORED_FILE.fullmatch(fname):
                    yield fname

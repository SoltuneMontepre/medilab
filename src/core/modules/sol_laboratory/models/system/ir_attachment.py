import os
import re
import tempfile
from datetime import UTC, datetime, timedelta

from odoo import api, models
from odoo.tools import config

from odoo.addons.sol_laboratory.constants.laboratory_bucket import (
    FILESTORE_GC_GRACE,
    FILESTORE_PREFIX,
    READ_CHUNK_SIZE,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.services import laboratory_bucket

STORED_FILE = re.compile(r"[0-9a-f]{2}/[0-9a-f]+")


# Tệp Đính Kèm
class IrAttachment(models.Model):
    _inherit = MODEL_IR_ATTACHMENT

    @api.model
    def _bucket_key(self, fname):
        return f"{FILESTORE_PREFIX}/{self.env.cr.dbname}/{fname}"

    @api.model
    def _file_write(self, fname, bin_value):
        super()._file_write(fname, bin_value)
        if laboratory_bucket.filestore_enabled():
            self._upload_file(fname)

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
        if laboratory_bucket.filestore_enabled() and (config["init"] or config["update"]):
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

    @api.model
    def _local_files(self):
        root = self._filestore()
        for folder, _folders, names in os.walk(root):
            for name in names:
                fname = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                if STORED_FILE.fullmatch(fname):
                    yield fname

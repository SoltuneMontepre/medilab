import io
import os
from unittest.mock import patch

from PIL import Image

from odoo.tests import TransactionCase, tagged
from odoo.tools import config, file_open
from odoo.tools.binary import BinaryBytes

from odoo.addons.sol_laboratory.constants.laboratory_bucket import FILESTORE_VARIABLE
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT

MODULE_IMAGE = "sol_laboratory/static/description/icon.png"


@tagged("post_install", "-at_install")
class TestModuleFiles(TransactionCase):
    """A file lost from the filestore is written again from the installed module that holds the same content."""

    def setUp(self):
        super().setUp()
        self.attachments = self.env[MODEL_IR_ATTACHMENT].sudo()
        environment = patch.dict(os.environ, {FILESTORE_VARIABLE: "0"})
        environment.start()
        self.addCleanup(environment.stop)
        with file_open(MODULE_IMAGE, "rb") as file:
            self.module_image = file.read()

    def image_attachments(self, partner):
        self.env.flush_all()
        return self.attachments.search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id), ("res_field", "!=", False)]
        )

    def lose(self, attachments):
        for fname in set(attachments.mapped("store_fname")):
            path = self.attachments._full_path(fname)
            if os.path.exists(path):
                os.unlink(path)
        self.env.invalidate_all()

    def upgrade(self):
        with patch.dict(config._runtime_options, {"update": ["sol_laboratory"]}):
            self.attachments._register_hook()
        self.env.invalidate_all()

    def test_a_lost_module_file_is_written_again(self):
        attachment = self.attachments.create({"name": "icon.png", "raw": self.module_image})
        self.lose(attachment)

        self.upgrade()

        self.assertEqual(bytes(attachment.raw), self.module_image)

    def test_the_images_stored_from_a_lost_module_file_are_written_again(self):
        partner = self.env["res.partner"].create({"name": "Logo owner", "image_1920": BinaryBytes(self.module_image)})
        attachments = self.image_attachments(partner)
        self.lose(attachments)
        self.assertEqual(len(attachments), 5)
        self.assertFalse(bytes(partner.image_128.content))

        self.upgrade()

        self.assertEqual(bytes(partner.image_1920.content), self.module_image)
        self.assertTrue(bytes(partner.image_128.content))
        for fname in attachments.exists().mapped("store_fname"):
            self.assertTrue(os.path.exists(self.attachments._full_path(fname)))

    def test_a_file_no_module_holds_stays_missing_and_its_images_are_kept(self):
        image = io.BytesIO()
        Image.new("RGB", (300, 200), tuple(os.urandom(3))).save(image, "PNG")
        partner = self.env["res.partner"].create({"name": "Uploaded logo", "image_1920": BinaryBytes(image.getvalue())})
        attachments = self.image_attachments(partner)
        self.lose(attachments)

        with self.assertLogs("odoo.addons.sol_laboratory.models.system.ir_attachment", "WARNING"):
            self.upgrade()

        self.assertEqual(self.image_attachments(partner), attachments)
        self.assertFalse(os.path.exists(self.attachments._full_path(attachments[0].store_fname)))

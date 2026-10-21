from datetime import timedelta

from odoo import fields
from odoo.fields import Command

from .laboratory_sample_folder_case import LaboratorySampleFolderCase
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE


class LaboratoryFileLocksCase(LaboratorySampleFolderCase):
    """A calibration file of the HPLC folder, which has no category, saved once by the tester, and the computer the
    tester locks it from."""

    def setUp(self):
        super().setUp()
        self.file = self.file_of("HPLC/calibration.csv")
        self.first = self.save(self.file, "calibration 1")
        self.computer, _key = self.sign_in(self.tester, "1b7e4c2a-0d3f-4e8a-9c61-5a2f7d9e0b14")

    def lock_as(self, user, file=None):
        return (file or self.file).with_user(user)._lock(self.computer if user == self.tester else None)

    def file_in(self, category, path="calibration.csv"):
        """A file saved once in a new folder of the category, of which the member is a member too."""
        folder = self.folder_of_category(
            category,
            name=f"HPLC {category or 'none'} {path.replace('.', ' ')}",
            member_ids=[Command.create({"user_id": self.member.id, "role": MEMBER_ROLE})],
        )
        file = self.file_of(path, folder)
        self.save(file, f"{path} 1")
        return file

    @staticmethod
    def pass_expiry(lock, minutes=1):
        lock.sudo().expires_at = fields.Datetime.now() - timedelta(minutes=minutes)

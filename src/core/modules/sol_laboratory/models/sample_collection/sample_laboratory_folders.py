from typing import TYPE_CHECKING

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, UserError
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.laboratory_files import PERMISSION_DENIED, RAW_DATA, RESULT, UPLOAD_ONLY
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER, MODEL_SAMPLE
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleLaboratoryFoldersBase
else:
    SampleLaboratoryFoldersBase = object

# The folders creating a sample's folders adds: its raw data and its results.
SAMPLE_FOLDER_CATEGORIES = (RAW_DATA, RESULT)


# Mẫu: the sample's laboratory folders.
class SampleLaboratoryFolders(models.Model, SampleLaboratoryFoldersBase):
    _inherit = MODEL_SAMPLE

    if not TYPE_CHECKING:
        # Number of the sample's laboratory folders the user sees.
        laboratory_folder_count = fields.Integer(compute="_compute_laboratory_folder_count")
        # True while the sample lacks its raw-data or result folder, whoever can see them.
        laboratory_folders_missing = fields.Boolean(compute="_compute_laboratory_folders_missing")

    @api.depends_context("uid")
    def _compute_laboratory_folder_count(self):
        folders = self.env[MODEL_LABORATORY_FOLDER]
        counts = dict(folders._read_group([("sample_id", "in", self.ids)], ["sample_id"], ["__count"]))
        for sample in self:
            sample.laboratory_folder_count = counts.get(sample, 0)

    def _compute_laboratory_folders_missing(self):
        folders = self.env[MODEL_LABORATORY_FOLDER].sudo()
        groups = folders._read_group(
            [("sample_id", "in", self.ids), ("category", "in", SAMPLE_FOLDER_CATEGORIES)], ["sample_id"], ["__count"]
        )
        complete = {sample for sample, count in groups if count == len(SAMPLE_FOLDER_CATEGORIES)}
        for sample in self:
            sample.laboratory_folders_missing = sample not in complete

    def action_create_laboratory_folders(self):
        """Add the raw-data and result folders the sample does not have yet, owned by the person who creates them."""
        self.ensure_one()
        self._check_can_create_laboratory_folders()
        self._create_laboratory_folders(self.env.user)
        return self.action_open_laboratory_folders()

    def action_open_laboratory_folders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sol_laboratory.action_medilab_laboratory_folder")
        action["domain"] = [("sample_id", "=", self.id)]
        return action

    def _check_can_create_laboratory_folders(self):
        """Refuse the user who may not create the samples' folders: the head of a department that tests the sample
        creates them from it, holding the laboratory files permission. Who creates a sample's folders, and when, is an
        open question; the answer changes only this method."""
        self.env[MODEL_LABORATORY_FOLDER]._check_laboratory_files_permission()
        self.check_access("read")
        for sample in self:
            # The head of a department is its manager.
            if self.env.user not in sample.sudo()._test_departments().manager_id.user_id:
                raise LaboratoryFileError(
                    PERMISSION_DENIED,
                    self.env._("Only the head of a department that tests %s creates its folders.", sample.code),
                )

    def _create_laboratory_folders(self, owner):
        """Add the raw-data and result folders each sample does not have yet and return them: owned by the owner,
        upload-only and without sync rules, so every file is synced. They are named after the lab code only, which
        testers see. Two creations at once make one folder of each category: the second one's creation fails on the
        unique key and Odoo runs its request again, which finds the folders."""
        folders = self.env[MODEL_LABORATORY_FOLDER].sudo()
        labels = dict(folders._fields["category"]._description_selection(self.env))
        created = folders.browse()
        for sample in self.sudo():
            existing = set(folders.search([("sample_id", "=", sample.id)]).mapped("category"))
            for category in SAMPLE_FOLDER_CATEGORIES:
                if category in existing:
                    continue
                root = f"{sample.code}-{category}"
                if folders.search_count([("owner_id", "=", owner.id), ("root", "=", root)], limit=1):
                    raise UserError(
                        self.env._("%(owner)s already has a folder named %(root)s.", owner=owner.name, root=root)
                    )
                created |= sample._create_laboratory_folder(
                    {
                        "name": f"{sample.code} {labels[category]}",
                        "root": root,
                        "owner_id": owner.id,
                        "sample_id": sample.id,
                        "category": category,
                        "sync_mode": UPLOAD_ONLY,
                    }
                )
        return created.with_env(self.env)

    def _create_laboratory_folder(self, vals):
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                return self.env[MODEL_LABORATORY_FOLDER].sudo().create(vals)
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Committed by a transaction this one cannot see; ConcurrencyError is what Odoo's request retrying retries.
            raise ConcurrencyError(
                self.env._("Another person created the folders of %s meanwhile; this is run again.", self.code)
            ) from error

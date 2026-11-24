from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskLaboratoryFilesBase

    from odoo.orm.types import DomainType
else:
    TaskLaboratoryFilesBase = object


# Nhiệm Vụ: a testing task opens the laboratory files of its sample.
class TaskLaboratoryFiles(models.Model, TaskLaboratoryFilesBase):
    _inherit = MODEL_TASK

    if not TYPE_CHECKING:
        # Number of laboratory files of a testing task's sample the user sees; 0 for any other task.
        laboratory_file_count = fields.Integer(compute="_compute_laboratory_file_count")

    def _testing_sample(self):
        """The sample of a testing task; empty for any other task. Only this hop runs as superuser, as a person reads
        their testing tasks without reading the sample test."""
        self.ensure_one()
        if not self.sudo().filtered_domain(self._testing_domain()):
            return self.env[MODEL_SAMPLE]
        return self.env[MODEL_SAMPLE_TEST].sudo().browse(self.document_id).sample_id.with_env(self.env)

    def _laboratory_files_domain(self) -> "DomainType":
        # "in" rather than "=": a task of no sample must match no file, not the files of folders of no sample.
        return [("folder_id.sample_id", "in", self._testing_sample().ids)]

    @api.depends("document_model", "document_id", "action", "type_id", "linked_by_system")
    @api.depends_context("uid")
    def _compute_laboratory_file_count(self):
        files = self.env[MODEL_LABORATORY_FILE]
        readable = files.has_access("read")
        for task in self:
            task.laboratory_file_count = files.search_count(task._laboratory_files_domain()) if readable else 0

    def action_open_laboratory_files(self):
        """Open the files of the task's sample, under the folders they are in."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sol_laboratory.action_medilab_laboratory_file")
        action["domain"] = self._laboratory_files_domain()
        action["context"] = {"search_default_group_by_folder": 1}
        return action

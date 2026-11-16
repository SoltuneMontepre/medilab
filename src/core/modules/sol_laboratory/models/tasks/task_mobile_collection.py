from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE, MODEL_TASK, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskCollectionMobileBase
else:
    TaskCollectionMobileBase = object

# The field of a sample that names the document a collection task is on.
SAMPLE_OF_DOCUMENT = {MODEL_SAMPLE: "id", MODEL_TEST_REQUEST: "request_id"}


# Nhiệm Vụ: the samples a sample collection task is for and where they are taken from, which Medilab Mobile shows so
# sample delivery staff open each sample to photograph it. It extends task_mobile, so it loads after it.
class TaskCollectionMobile(models.Model, TaskCollectionMobileBase):
    _name = MODEL_TASK
    _inherit = MODEL_TASK

    def _collection_samples(self):
        """The samples the collection task is for, as the person may read them: its sample, or the samples of its test
        request. Any other task is for none."""
        self.ensure_one()
        samples = self.env[MODEL_SAMPLE]
        field = SAMPLE_OF_DOCUMENT.get(self.document_model or "")
        if not field or not self.document_id or self.sudo().type_id.code != SAMPLE_COLLECTION_CODE:
            return samples
        return samples.search([(field, "=", self.document_id)], order="code, id")

    def _mobile_values(self):
        """A collection task's place is where its samples are taken from, when the task has no other."""
        values = super()._mobile_values()
        for task, task_values in zip(self, values, strict=True):
            if not task_values["location"]:
                locations = task._collection_samples().sampling_location_id
                task_values["location"] = ", ".join(location.display_name or "" for location in locations)
        return values

    def _mobile_detail(self):
        detail = super()._mobile_detail()
        detail["samples"] = [
            {
                "id": sample.id,
                "code": sample.code or "",
                "sampling_location": sample.sampling_location_id.display_name or "",
            }
            for sample in self._collection_samples()
        ]
        return detail

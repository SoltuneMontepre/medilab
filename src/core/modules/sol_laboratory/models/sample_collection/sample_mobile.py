from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.medilab_mobile import ALREADY_CLAIMED
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_SAMPLE, MODEL_SAMPLE_HANDOVER, MODEL_TASK
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import not_found

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleMobileBase
else:
    SampleMobileBase = object


# Mẫu: what Medilab Mobile reads of a sample whose label it scans, and the testing tasks it claims on it, with the
# person's rights.
class SampleMobile(models.Model, SampleMobileBase):
    _name = MODEL_SAMPLE
    _inherit = MODEL_SAMPLE

    @api.model
    def _from_label(self, code):
        """The sample of the lab code the person may read; one they may not read is not found."""
        sample = self.search([("code", "=", (code or "").strip())], limit=1)
        if not sample:
            raise not_found(self.env)
        return sample

    def _mobile_detail(self):
        """The sample as the person may see it, with its handover to their department and the testing tasks of their
        department's queue on it. Only a person who reads every test request sees the customer and the customer's name
        for the sample, as on the web."""
        self.ensure_one()
        sample = self
        customer_visible = self.env.su or self.env.user.has_group(TEST_REQUEST_READER_GROUP)
        states = dict(sample._fields["physical_state"]._description_selection(self.env))
        statuses = dict(sample._fields["status"]._description_selection(self.env))
        return {
            "id": sample.id,
            "code": sample.code,
            "status": statuses[sample.status],
            "sample_type": sample.sample_type_id.display_name or "",
            "physical_state": states.get(sample.physical_state, ""),
            "form": sample.sample_form or "",
            "container": sample.container_type or "",
            "received_at": api_datetime(sample.received_at),
            "storage_location": sample.storage_location or "",
            "sampling_location": sample.sampling_location_id.display_name or "",
            "note": sample.note or "",
            "customer": sample.sudo().request_id.customer_id.display_name if customer_visible else None,
            "customer_sample_name": sample.sudo().customer_sample_name if customer_visible else None,
            "handover": sample._mobile_handover(),
            "tasks": sample._claimable_testing_tasks()._mobile_values(),
        }

    def _mobile_handover(self):
        """The sample's handover to the person's department, as they may read it; None when there is none."""
        self.ensure_one()
        department = self.env[MODEL_PERSON]._current().department_id
        if not department:
            return None
        handover = self.env[MODEL_SAMPLE_HANDOVER].search(
            [("sample_id", "=", self.id), ("department_id", "=", department.id)], limit=1
        )
        if not handover:
            return None
        return {
            "department": department.name,
            "received_at": api_datetime(handover.received_at),
            # The person who received it is read with full rights, as the web's handover list shows it.
            "received_by": handover.sudo().received_by_id.name or "",
        }

    def _testing_tasks_domain(self):
        """The testing tasks the system opened on the sample's tests in the person's own department."""
        department = self.env[MODEL_PERSON]._current().department_id
        if not department:
            return Domain.FALSE
        return (
            self.env[MODEL_TASK]._testing_domain()
            & Domain("document_id", "in", self.sudo().test_ids.ids)
            & Domain("department_id", "=", department.id)
        )

    def _claimable_testing_tasks(self):
        """The sample's unassigned testing tasks waiting in the person's own department's queue."""
        self.ensure_one()
        return self.env[MODEL_TASK].search(
            self._testing_tasks_domain() & Domain("in_my_queue", "=", True), order="deadline, id"
        )

    def _claim_from_phone(self, task_ids):
        """Claim the listed testing tasks of the sample, which must all wait in the person's own department's queue.
        A task someone else claimed first is refused as already claimed; any other task as refused."""
        self.ensure_one()
        claimable = self._claimable_testing_tasks()
        tasks = claimable.browse(task_ids)
        refused = tasks - claimable
        if refused:
            ours = self.env[MODEL_TASK].sudo().search(self._testing_tasks_domain() & Domain("id", "in", refused.ids))
            taken = ours.with_env(self.env).filtered(lambda task: task._claimed_by_someone_else())
            if taken:
                raise LaboratoryFileError(
                    ALREADY_CLAIMED,
                    self.env._("%s is already claimed.", format_list(self.env, taken.sudo().mapped("name"))),
                )
            raise UserError(
                self.env._("Only the unassigned testing tasks of your department on %s can be claimed here.", self.code)
            )
        try:
            tasks.action_claim()
        except UserError as error:
            if any(task._claimed_by_someone_else() for task in tasks):
                raise LaboratoryFileError(ALREADY_CLAIMED, error.args[0]) from error
            raise
        return tasks

from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    IDEMPOTENCY_CONFLICT,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.medilab_mobile import ALREADY_CLAIMED, PHOTO_MAX_BYTES
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_ATTACHMENT,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_HANDOVER,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import not_found
from odoo.addons.sol_laboratory.services.mobile_uploads import decoded_base64

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleMobileBase
else:
    SampleMobileBase = object


# Mẫu: what Medilab Mobile reads of a sample whose label it scans, the testing tasks it claims on it and the photos it
# attaches to it, with the person's rights.
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
        customer_visible = self._customer_visible()
        states = dict(sample._fields["physical_state"]._description_selection(self.env))
        statuses = dict(sample._fields["status"]._description_selection(self.env))
        return {
            "id": sample.id,
            "code": sample.code or "",
            "status": statuses.get(sample.status or "", ""),
            "sample_type": sample.sample_type_id.display_name or "",
            "physical_state": states.get(sample.physical_state or "", ""),
            "form": sample.sample_form or "",
            "container": sample.container_type or "",
            "received_at": api_datetime(sample.received_at),
            "storage_location": sample.storage_location or "",
            "sampling_location": sample.sampling_location_id.display_name or "",
            "note": sample.note or "",
            "customer": (sample.sudo().request_id.customer_id.display_name or "") if customer_visible else None,
            "customer_sample_name": (sample.sudo().customer_sample_name or "") if customer_visible else None,
            "handover": sample._mobile_handover(),
            "tasks": sample._claimable_testing_tasks()._mobile_values(),
            "can_add_photos": sample._may_add_photos(),
            "tests_samples": self._person_tests_samples(),
        }

    @api.model
    def _person_tests_samples(self):
        """Whether the person tests samples: they are in a department and the Lab Head authorized them to test a
        parameter, so their department receives samples and its testing tasks reach them."""
        person = self.env[MODEL_PERSON]._current()
        if not person.department_id:
            return False
        return bool(
            self.env[MODEL_PARAMETER_AUTHORIZATION].sudo().search_count([("person_id", "=", person.id)], limit=1)
        )

    def _customer_visible(self):
        """Whether the person reads every test request, and so sees a sample's customer and its photos, as on the web."""
        return self.env.su or self.env.user.has_group(TEST_REQUEST_READER_GROUP)

    def _may_add_photos(self):
        """Whether the person sees the sample's photos and may change the sample, which attaching a photo needs."""
        self.ensure_one()
        return self._customer_visible() and bool(self._filtered_access("write"))

    def _mobile_photos(self):
        """The sample's photos the person may read; a tester reads none."""
        self.ensure_one()
        if not self._customer_visible():
            return self.env[MODEL_IR_ATTACHMENT]
        return self.photo_ids.sorted("id", reverse=True)

    def _attach_photo_from_phone(self, device, values, key=None):
        """Attach the photo the phone took when the sample was collected or received, as action_attach_photo() does. A
        request repeated with its Idempotency-Key gets the photo it attached."""
        self.ensure_one()
        photo = _decoded_photo(self.env, values["data"])
        attachments = self.env[MODEL_IR_ATTACHMENT]
        created = attachments._created_with_key(device, key)
        if created:
            sent = created.sudo()
            if (sent.res_model, sent.res_id, sent.checksum) != (self._name, self.id, sent._compute_checksum(photo)):
                raise LaboratoryFileError(
                    IDEMPOTENCY_CONFLICT, self.env._("This Idempotency-Key was already sent with another request.")
                )
            return created
        if not self._may_add_photos():
            raise LaboratoryFileError(PERMISSION_DENIED, self.env._("You may not add photos to %s.", self.code))
        values = self._photo_values(photo, values["name"], values["mimetype"])
        return self._link_photo(attachments._create_once(device, key, values))

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
            # Recording the receipt needs the permission to edit the handover, which receive_by_label() checks.
            "can_receive": not handover.received_at and bool(handover._filtered_access("write")),
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


def _decoded_photo(env, data):
    """The photo the phone sent in base64; one over the limit is refused before it is decoded."""
    return decoded_base64(
        data,
        PHOTO_MAX_BYTES,
        env._("A photo can be at most 10 MiB."),
        env._("The photo is not valid base64."),
    )

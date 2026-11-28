from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PERSON,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestCollectionBase
else:
    TestRequestCollectionBase = object


# Yêu Cầu Thử Nghiệm: sample collection appointment, collector and customer contact shown on the request.
class TestRequestCollection(models.Model, TestRequestCollectionBase):
    _inherit = MODEL_TEST_REQUEST

    if not TYPE_CHECKING:
        # Number of sample collection tasks created for this request.
        collection_task_count = fields.Integer(compute="_compute_collection_info", compute_sudo=True)
        # Scheduled appointment window of the current or latest sample collection task.
        collection_appointment_display = fields.Char(
            string="Collection Appointment", compute="_compute_collection_info", compute_sudo=True
        )
        # Address where samples are collected for this request.
        collection_place = fields.Char(
            string="Collection Address", compute="_compute_collection_info", compute_sudo=True
        )
        # Sample delivery staff member assigned to the collection task.
        collection_assignee_id = fields.Many2one(
            MODEL_PERSON, string="Collector", compute="_compute_collection_info", compute_sudo=True
        )
        # True when the current user can open the sample collection tasks linked to this request.
        can_open_collection_tasks = fields.Boolean(compute="_compute_can_open_collection_tasks")
        # Name and phone number of the request's contact: its report recipient, or else the customer.
        customer_contact_display = fields.Char(string="Customer Contact", compute="_compute_customer_contact_display")

    def _collection_tasks_by_request(self, tasks):
        """Return matching sample collection tasks indexed by request id."""
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        all_tasks = (
            tasks.search(
                [
                    ("type_id", "=", task_type.id),
                    ("document_model", "=", MODEL_TEST_REQUEST),
                    ("document_id", "in", self.ids),
                ],
                order="id desc",
            )
            if self.ids and task_type
            else tasks.browse()
        )
        by_request = {}
        for task in all_tasks:
            by_request.setdefault(task.document_id, tasks.browse())
            by_request[task.document_id] |= task
        return by_request

    @api.depends("status")
    def _compute_collection_info(self):
        tasks = self.env[MODEL_TASK].sudo()
        by_request = self._collection_tasks_by_request(tasks)
        for request in self:
            req_tasks = by_request.get(request.id, tasks)
            open_tasks = req_tasks.filtered(lambda t: t.status not in ("done", "cancelled"))
            current = (open_tasks or req_tasks)[:1]
            request.collection_task_count = len(req_tasks)
            request.collection_appointment_display = current._appointment_display() if current else False
            request.collection_place = current.place if current else False
            request.collection_assignee_id = current.assignee_id if current else False

    @api.depends("status")
    @api.depends_context("uid")
    def _compute_can_open_collection_tasks(self):
        tasks = self.env[MODEL_TASK]
        by_request = self._collection_tasks_by_request(tasks)
        for request in self:
            request.can_open_collection_tasks = bool(by_request.get(request.id))

    @api.depends(
        "report_recipient_id.name",
        "report_recipient_id.phone",
        "report_recipient_id.parent_id.phone",
        "customer_id.partner_id.name",
        "customer_id.partner_id.phone",
    )
    def _compute_customer_contact_display(self):
        for request in self:
            partner = request.report_recipient_id or request.customer_id.partner_id
            phone = partner.phone or partner.parent_id.phone
            request.customer_contact_display = f"{partner.name}, {phone}" if phone else (partner.name or False)

    def action_open_collection_tasks(self):
        """Open sample collection tasks linked to this test request."""
        self.ensure_one()
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Sample Collection"),
            "res_model": MODEL_TASK,
            "view_mode": "list,form",
            "domain": [
                ("type_id", "=", task_type.id),
                ("document_model", "=", MODEL_TEST_REQUEST),
                ("document_id", "=", self.id),
            ],
            "context": {"create": False},
        }

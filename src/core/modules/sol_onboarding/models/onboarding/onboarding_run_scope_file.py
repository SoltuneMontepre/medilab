from typing import TYPE_CHECKING
from urllib.parse import quote

from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.onboarding import (
    CRAWL_JOB,
    KIND_TESTING_METHOD,
    MAX_BYTES,
    SCOPE_FILE_ADAPTER,
)
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.services.adapters.registry import adapter_for

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_onboarding_run as OnboardingRunScopeFileBase
else:
    OnboardingRunScopeFileBase = object


# Lượt Thu Thập: the accreditation scope file the laboratory uploads.
class OnboardingRunScopeFile(models.Model, OnboardingRunScopeFileBase):
    _inherit = MODEL_ONBOARDING_RUN

    if not TYPE_CHECKING:
        # The laboratory's list of accredited tests, as a PDF, staged as its accreditation scope.
        scope_file = fields.Binary(string="Scope File", attachment=True, copy=False)
        # File name of the scope file.
        scope_filename = fields.Char(string="Scope File Name", copy=False)

    def _scope_source(self):
        """The source whose adapter reads scope files, turned on or not: reading a file reaches no site."""
        return (
            self.env[MODEL_ONBOARDING_SOURCE]
            .sudo()
            .with_context(active_test=False)
            .search([("adapter", "=", SCOPE_FILE_ADAPTER)], order="id", limit=1)
        )

    def _scope_body(self) -> bytes:
        return bytes(self.scope_file or b"")

    def _scope_fetched(self) -> Fetched:
        """The scope file as a fetched document, whose address downloads it from the run."""
        name = quote(self.scope_filename or "scope.pdf")
        address = f"/web/content/{self._name}/{self.id}/scope_file/{name}?download=true"
        return Fetched(address, "pdf", self._scope_body(), fields.Datetime.now())

    def _scope_records(self) -> tuple[StagedValues, ...]:
        return adapter_for(self._scope_source()).uploaded_scope(self._scope_body())

    def _check_scope_file(self):
        """Refuse a scope file that is not a readable list of accredited tests, or that is of another organisation
        than the one chosen. With none chosen, the listed organisation with the file's accreditation number becomes
        the run's, so the run reads the source for it and what the source publishes is staged beside the file."""
        self.ensure_one()
        body = self._scope_body()
        if len(body) > MAX_BYTES:
            raise ValidationError(self.env._("The scope file is over 10 MB."))
        records = self._scope_records() if body.startswith(b"%PDF") else ()
        if not any(record.kind == KIND_TESTING_METHOD for record in records):
            raise ValidationError(
                self.env._("The scope file must be a PDF with the text of a list of accredited tests.")
            )
        code = next((record.parent[1] for record in records if record.parent), "")
        chosen = self.organisation_id
        if not code:
            return
        if chosen.accreditation_code and not chosen.filtered_domain([("accreditation_code", "=ilike", code)]):
            raise ValidationError(
                self.env._(
                    "The scope file is of %(file)s, and the organisation chosen is %(organisation)s.",
                    file=code,
                    organisation=chosen.accreditation_code,
                )
            )
        if not chosen:
            self.organisation_id = (
                self.env[MODEL_ONBOARDING_ORGANISATION]
                .sudo()
                .search([("source_id", "=", self._scope_source().id), ("accreditation_code", "=ilike", code)], limit=1)
            )

    def _queue_scope_file(self):
        """Queue the scope file as a page of the run, after the first pages of its organisation."""
        self.env[MODEL_SCHEDULED_JOB].queue(
            CRAWL_JOB,
            f"{self.id}:{self.scope_filename or 'scope.pdf'}",
            document=self,
            payload={"source_id": self._scope_source().id, "sector": None, "upload": True},
        )

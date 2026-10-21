import re
from collections.abc import Iterable

from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORGANISATION, MODEL_ONBOARDING_SOURCE
from odoo.addons.sol_onboarding.constants.onboarding import SUGGEST_CONTEXT
from odoo.addons.sol_onboarding.constants.xml_ids import SOURCES_GROUP
from odoo.addons.sol_onboarding.services.adapters.base import OrganisationValues


# Tổ Chức
class OnboardingOrganisation(models.Model):
    _name = MODEL_ONBOARDING_ORGANISATION
    _description = "Onboarding Organisation"
    _order = "name, id"

    _key_unique = models.Constraint("UNIQUE(source_id, external_key)", "A source lists an organisation once.")

    # The source that lists the organisation; only the developers see it.
    source_id = fields.Many2one(
        MODEL_ONBOARDING_SOURCE, string="Source", required=True, ondelete="cascade", groups=SOURCES_GROUP
    )
    # Key of the organisation at the source.
    external_key = fields.Char(string="External Key", required=True)
    # Organisation name as the source gives it.
    name = fields.Char(string="Name", required=True, index="trigram")
    # Tax ID of the organisation, when the source gives it.
    tax_id = fields.Char(string="Tax ID", index=True)
    # Accreditation number, such as VILAS 123, when the source gives it.
    accreditation_code = fields.Char(string="Accreditation Code")
    # Address of the organisation's page at the source.
    url = fields.Char(string="Address", required=True)
    # Time the organisation was last seen at the source.
    seen_at = fields.Datetime(string="Seen At", required=True)
    # False when the source no longer lists the organisation.
    active = fields.Boolean(string="Active", default=True)

    def _upsert(self, source, values: Iterable[OrganisationValues]):
        """Create or update the source's organisations by key, mark them seen now and bring archived ones back."""
        now = fields.Datetime.now()
        organisations = self.sudo().with_context(active_test=False)
        existing = {
            organisation.external_key: organisation
            for organisation in organisations.search([("source_id", "=", source.id)])
        }
        result = organisations
        for value in values:
            vals = {
                "name": value.name,
                "tax_id": value.tax_id,
                "accreditation_code": value.accreditation_code,
                "url": value.url,
                "seen_at": now,
                "active": True,
            }
            organisation = existing.get(value.key)
            if organisation:
                organisation.write(vals)
            else:
                organisation = organisations.create({**vals, "source_id": source.id, "external_key": value.key})
                existing[value.key] = organisation
            result |= organisation
        return result

    def _suggested(self, company, limit=20, domain=None):
        """Active organisations for the company, its tax ID first, then the closest name."""
        tax_digits = re.sub(r"\D", "", company.vat or "")
        tax_order = (
            SQL(r"regexp_replace(coalesce(tax_id, ''), '\D', '', 'g') = %s DESC, ", tax_digits)
            if tax_digits
            else SQL("")
        )
        self.flush_model()
        self.env.cr.execute(
            SQL(
                "SELECT id FROM %(table)s WHERE active AND id IN %(allowed)s ORDER BY %(tax_order)s similarity(name, %(name)s) DESC, name "
                "LIMIT %(limit)s",
                table=SQL.identifier(self._table),
                allowed=self._search(domain or []).subselect(),
                tax_order=tax_order,
                name=company.name or "",
                limit=limit,
            )
        )
        return self.browse([row[0] for row in self.env.cr.fetchall()])

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        if name or not self.env.context.get(SUGGEST_CONTEXT):
            return super().name_search(name, domain, operator, limit)
        suggested = self._suggested(self.env.company, limit, domain)
        return [(organisation.id, organisation.display_name) for organisation in suggested]

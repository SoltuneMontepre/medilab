from urllib.parse import urljoin

from odoo.addons.sol_onboarding.constants.onboarding import VALUE_KEYS
from odoo.addons.sol_onboarding.services.adapters.base import Adapter, OrganisationValues, Parsed, StagedValues
from odoo.addons.sol_onboarding.services.adapters.registry import register
from odoo.addons.sol_onboarding.services.parsing import clean_text, html_tree


# Reads the simple recorded pages of the tests.
@register("pages")
class PagesAdapter(Adapter):
    sectors = ("food",)

    def organisation_list_pages(self):
        return [self.source.start_url]

    def organisation_pages(self, organisation):
        return [organisation.url]

    def sector_pages(self, sector):
        return [f"https://{self.source.host}/{sector}"]

    def parse(self, document, sector):
        tree = html_tree(document.body)
        organisations = tuple(
            OrganisationValues(
                key=row.get("data-key"),
                name=clean_text(row.text_content()),
                url=document.url,
                tax_id=row.get("data-tax-id"),
                accreditation_code=row.get("data-code"),
            )
            for row in tree.xpath("//tr[@data-key]")
        )
        records = []
        for item in tree.xpath("//li[@data-kind]"):
            kind = item.get("data-kind")
            parent = (
                (item.get("data-parent-kind"), item.get("data-parent-key")) if item.get("data-parent-key") else None
            )
            records.append(
                StagedValues(
                    kind=kind,
                    key=item.get("data-key"),
                    values={key: clean_text(item.get(f"data-{key.replace('_', '-')}", "")) for key in VALUE_KEYS[kind]},
                    lang="vi_VN",
                    sector=sector,
                    parent=parent,
                )
            )
        links = tuple(urljoin(document.url, link.get("href")) for link in tree.xpath('//a[@rel="next"]'))
        return Parsed(tuple(records), organisations, links)

import re

from odoo.addons.sol_onboarding.constants.onboarding import KIND_TESTING_FIELD, KIND_TESTING_METHOD
from odoo.addons.sol_onboarding.services.adapters.base import Adapter, Fetched, Parsed, StagedValues
from odoo.addons.sol_onboarding.services.adapters.registry import register
from odoo.addons.sol_onboarding.services.fetcher import PageSkipped
from odoo.addons.sol_onboarding.services.parsing import clean_text, html_tree

FIELD_KEY = "Microbiology"
CHAPTER_HEADER = "Chapter No."
CHAPTER = re.compile(r"\d+[A-Z]?")


# Reads the chapter index of the FDA Bacteriological Analytical Manual, which serves food and cosmetics alike.
@register("fda_bam")
class FdaBamAdapter(Adapter):
    sectors = ("food", "cosmetics")

    def organisation_list_pages(self):
        return []

    def sector_pages(self, sector):
        return [self.source.start_url]

    def parse(self, document: Fetched, sector: str | None) -> Parsed:
        chapters = list(_chapters(html_tree(document.body)))
        if not chapters:
            raise PageSkipped(self.source.env._("no chapter table"))
        field = StagedValues(KIND_TESTING_FIELD, FIELD_KEY, {"code": "", "name": FIELD_KEY}, "en_US", sector)
        methods = []
        for number, title in chapters:
            code = f"FDA BAM Ch. {number}"
            values = {"code": code, "name": title, "field_key": FIELD_KEY}
            methods.append(StagedValues(KIND_TESTING_METHOD, code, values, "en_US", sector))
        return Parsed((field, *methods))


# The (chapter, title) rows of the chapter table; appendices do not match the chapter pattern.
def _chapters(tree):
    for table in tree.iter("table"):
        header = next(table.iter("th"), None)
        if header is None or clean_text(header.text_content()) != CHAPTER_HEADER:
            continue
        for row in table.iter("tr"):
            number, cell = row.find("th"), row.find("td")
            if number is None or cell is None or row.getparent().tag != "tbody":
                continue
            number = clean_text(number.text_content())
            link = next(cell.iter("a"), None)
            title = clean_text((cell if link is None else link).text_content())
            if CHAPTER.fullmatch(number) and title:
                yield number, title

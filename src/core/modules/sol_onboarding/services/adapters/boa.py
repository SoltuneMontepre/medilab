import re
from datetime import datetime
from itertools import pairwise, takewhile
from urllib.parse import urljoin, urlsplit

from odoo.addons.sol_onboarding.constants.onboarding import KIND_CERTIFICATE, KIND_TESTING_FIELD, KIND_TESTING_METHOD
from odoo.addons.sol_onboarding.services.adapters.base import (
    Adapter,
    Fetched,
    OrganisationValues,
    Parsed,
    StagedValues,
)
from odoo.addons.sol_onboarding.services.adapters.registry import register
from odoo.addons.sol_onboarding.services.parsing import clean_text, html_tree, pdf_text

ISSUING_BODY = "BoA"
CODE_LABEL = "Mã số công nhận"
VALID_UNTIL_LABEL = "Ngày hiệu lực"
SCOPE_ID = "tochuc-congnhan"
ANNEX_TITLE = "LIST OF ACCREDITED TESTS"
METHOD_CODE = re.compile(
    r"\b(TCVN|ISO|ASTM|GOST|AOAC|SMEWW|EN|IEC|EPA|USP|BS|DIN|JIS|NF)\s+"
    r"([A-Z]{0,2}\s?\d+(?:[.\-]\d+)*)"  # number, such as D 1500, 9.054 or 6579-1
    r"(?:\s*([-:])\s*(\d{2,4}[a-z]*\d*))?"  # version, such as -12a, -21e1 or :2019
    r"(?:\s*\(\s*(e?\d{4})\s*\))?"  # reapproval year, such as (2019) or (e2003)
)
ROW = re.compile(r"^\s*(\d{1,3})\.(?=\s|$)", re.M)
FIELD = re.compile(r"Lĩnh vực thử nghiệm\s*:\s*(.+?)\s*\n\s*Field of testing\s*:\s*(.+)")
CERTIFICATE_CODE = re.compile(r"Code\s*:\s*([A-Z][A-Z ]*\d+)")
ENGLISH_START = re.compile(
    r"\b(Determination|Measur\w*|Test\w*|Analysis|Detection|Enumeration|Identification|Quantification|Calculation)\b"
)
# A word that starts with a number, such as a limit of quantitation, ends a method's title.
TITLE_END = re.compile(r"\(?\d")


# Reads the organisation search of the Bureau of Accreditation, an organisation's page and its accreditation scope.
@register("boa")
class BoaAdapter(Adapter):
    def organisation_list_pages(self):
        return [self.source.start_url]

    def organisation_pages(self, organisation):
        return [organisation.url]

    def parse(self, document: Fetched, sector: str | None) -> Parsed:
        if document.content_type == "pdf":
            return Parsed(self._annex(pdf_text(document.body)))
        tree = html_tree(document.body)
        if urlsplit(document.url).path == urlsplit(self.source.start_url).path:
            return self._organisation_list(tree, document.url)
        return self._organisation_page(tree, document.url)

    def _organisation_list(self, tree, url: str) -> Parsed:
        organisations = []
        for row in tree.find_class("views-row"):
            link = next(row.iter("a"), None)
            name, unit = _text(row, "tochuc-ten"), _text(row, "tochuc-dvcq")
            if link is None or not link.get("href") or not name:
                continue
            address = urljoin(url, link.get("href"))
            organisations.append(
                OrganisationValues(
                    key=urlsplit(address).path.rstrip("/").rpartition("/")[2],
                    name=f"{name} ({unit})" if unit and unit != name else name,
                    url=address,
                    accreditation_code=_text(row, "stt-item") or None,
                )
            )
        links = tuple(urljoin(url, a.get("href")) for a in tree.iter("a") if a.get("rel") == "next" and a.get("href"))
        return Parsed(organisations=tuple(organisations), links=links)

    def _organisation_page(self, tree, url: str) -> Parsed:
        labels = {}
        for label in tree.find_class("label-maso"):
            value = label.getnext()
            labels[clean_text(label.text_content())] = "" if value is None else clean_text(value.text_content())
        records = ()
        if code := labels.get(CODE_LABEL):
            values = {
                "code": code,
                "issuing_body": ISSUING_BODY,
                "valid_from": "",
                "valid_until": _iso_date(labels.get(VALID_UNTIL_LABEL, "")),
            }
            records = (StagedValues(KIND_CERTIFICATE, code, values, "vi_VN"),)
        scope = tree.get_element_by_id(SCOPE_ID, None)
        hrefs = [] if scope is None else [urljoin(url, a.get("href", "")) for a in scope.iter("a")]
        links = tuple(dict.fromkeys(href for href in hrefs if urlsplit(href).path.lower().endswith(".pdf")))
        return Parsed(records, links=links)

    def _annex(self, text: str) -> tuple[StagedValues, ...]:
        """The testing fields and methods of a list of accredited tests, fields first; nothing for any other text."""
        if ANNEX_TITLE not in text:
            return ()
        certificate = CERTIFICATE_CODE.search(text)
        parent = (KIND_CERTIFICATE, clean_text(certificate.group(1))) if certificate else None
        headers = [
            (match.start(), clean_text(match.group(1)), clean_text(match.group(2))) for match in FIELD.finditer(text)
        ]
        testing_fields = {}
        for _start, key, name in headers:
            testing_fields.setdefault(key, StagedValues(KIND_TESTING_FIELD, key, {"code": "", "name": name}, "en_US"))
        methods = {}
        bounds = [match.start() for match in ROW.finditer(text)] + [len(text)]
        for start, end in pairwise(bounds):
            segment = text[start:end]
            field_key = next((key for at, key, _name in reversed(headers) if at < start), "")
            title = _title(segment)
            for match in METHOD_CODE.finditer(segment):
                code = _code(match)
                values = {"code": code, "name": title or code, "field_key": field_key}
                methods.setdefault(code, StagedValues(KIND_TESTING_METHOD, code, values, "en_US", parent=parent))
        return (*testing_fields.values(), *methods.values())


def _text(row, class_name: str) -> str:
    return clean_text(" ".join(element.text_content() for element in row.find_class(class_name)))


def _iso_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def _code(match: re.Match) -> str:
    body, number, separator, version, year = match.groups()
    code = f"{body} {''.join(number.split())}"
    if version:
        code += f"{separator}{version}"
    if year:
        code += f" ({year})"
    return code


# The English test name of a row, from its first English word to the first word that is not English text.
def _title(segment: str) -> str:
    text = clean_text(METHOD_CODE.sub(" ", segment))
    start = ENGLISH_START.search(text)
    if not start:
        return ""
    words = text[start.start() :].split()
    return " ".join(takewhile(lambda word: word.isascii() and not TITLE_END.match(word), words))

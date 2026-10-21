from dataclasses import dataclass
from datetime import datetime


# A page or file read from a source.
@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str  # "html", "pdf", "json" ("text" for robots.txt only)
    body: bytes
    fetched_at: datetime


@dataclass(frozen=True)
class OrganisationValues:
    key: str
    name: str
    url: str
    tax_id: str | None = None
    accreditation_code: str | None = None


@dataclass(frozen=True)
class StagedValues:
    kind: str  # a KIND_* constant
    key: str
    values: dict[str, str]  # VALUE_KEYS[kind], plain text
    lang: str
    sector: str | None = None  # a SECTOR_CODES entry
    parent: tuple[str, str] | None = None  # (kind, key) of the staged record it belongs to


@dataclass(frozen=True)
class Parsed:
    records: tuple[StagedValues, ...] = ()
    organisations: tuple[OrganisationValues, ...] = ()
    links: tuple[str, ...] = ()


# What a source's adapter tells the crawler: which pages to read and how to read each.
class Adapter:
    sectors: tuple[str, ...] = ()  # sector codes the source lists pages for

    def __init__(self, source):
        self.source = source

    def organisation_list_pages(self) -> list[str]:
        raise NotImplementedError

    def organisation_pages(self, organisation) -> list[str]:
        raise NotImplementedError

    def sector_pages(self, sector: str) -> list[str]:
        raise NotImplementedError

    def parse(self, document: Fetched, sector: str | None) -> Parsed:
        raise NotImplementedError

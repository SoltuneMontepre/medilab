"""Read-only parsing of fetched documents: nothing here opens a network connection."""

import json
import unicodedata
from io import BytesIO

from lxml import html

from odoo.tools.pdf import PdfReader


# Folds compatibility forms, drops control characters and collapses whitespace.
def clean_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = "".join(
        " " if char.isspace() else char for char in text if char.isspace() or unicodedata.category(char)[0] != "C"
    )
    return " ".join(text.split())


def html_tree(body: bytes):
    return html.fromstring(body, parser=html.HTMLParser(no_network=True, remove_comments=True))


# Text of a PDF; empty for a scanned or unreadable one.
def pdf_text(body: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(body), strict=False)
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception:  # fetched PDFs are untrusted: any reader failure means no text
        return ""


def json_data(body: bytes):
    return json.loads(body)

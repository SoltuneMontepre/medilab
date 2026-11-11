"""Converts a DOCX document to PDF with ONLYOFFICE Document Server's conversion API, at its internal address. Document
Server reads the DOCX from a presigned address of its content and answers with the address of the PDF, which Odoo
fetches as it fetches a saved document: only from the editing service, within the same limits."""

import os

import requests

from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE, JWT_HEADER
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import BEARER, jwt_secret, sign
from odoo.addons.sol_laboratory.services.saved_documents import (
    SavedDocumentRefused,
    SavedDocumentTooLarge,
    SavedDocumentUnavailable,
    saved_document,
)

CONVERTER_PATH = "/converter"
# Seconds to connect and to wait for Document Server to finish converting.
TIMEOUT = 120
# Seconds the signed request is valid.
TOKEN_SECONDS = 300


class ConversionUnavailable(Exception):
    """Document Server did not convert the document now; a later attempt can."""


def convert_to_pdf(document_url, key, title):
    """The PDF bytes of the DOCX at document_url. The key names the conversion, so the same content converted again is
    answered from Document Server's cache."""
    service_url = os.environ.get(INTERNAL_URL_VARIABLE)
    secret = jwt_secret()
    if not service_url or not secret:
        raise ConversionUnavailable("The editing service is not configured.")
    payload = {"async": False, "filetype": "docx", "outputtype": "pdf", "key": key, "title": title, "url": document_url}
    token = sign(payload, secret, TOKEN_SECONDS)
    try:
        response = requests.post(
            f"{service_url.rstrip('/')}{CONVERTER_PATH}",
            json={**payload, "token": token},
            headers={"Accept": "application/json", JWT_HEADER: BEARER + token},
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        answer = response.json() if response.status_code == 200 else {}
    except (requests.RequestException, ValueError) as error:
        raise ConversionUnavailable(f"The editing service did not answer: {type(error).__name__}.") from None
    answer = answer if isinstance(answer, dict) else {}
    if answer.get("error") or not answer.get("endConvert") or not answer.get("fileUrl"):
        raise ConversionUnavailable(f"The editing service did not convert the document: {answer.get('error', '')}.")
    try:
        with saved_document(answer["fileUrl"]) as chunks:
            return b"".join(chunks)
    except (SavedDocumentRefused, SavedDocumentTooLarge, SavedDocumentUnavailable) as error:
        raise ConversionUnavailable(str(error)) from None

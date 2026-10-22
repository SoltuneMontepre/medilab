"""Streams a document the editing service saved, from its internal address only and in chunks, so a callback cannot make
Odoo fetch from anywhere else and a document of up to 5 GiB is never held whole in memory. Storing the chunks is the
caller's; the errors below stop the stream wherever the caller is in it."""

import time
from contextlib import contextmanager

import requests

from odoo.addons.sol_laboratory.services.editing_service_urls import internal_saved_document_url

# The largest saved document fetched, as files reach 5 GiB.
MAX_SIZE = 5 * 1024**3
CHUNK_SIZE = 1024 * 1024
# Seconds to connect, and to wait for each read.
TIMEOUT = 60
# Seconds the whole fetch may take, within the time limit of Odoo's workers.
TOTAL_SECONDS = 900


class SavedDocumentRefused(Exception):
    """The address is not one of the editing service's, or redirects elsewhere; it is never fetched."""


class SavedDocumentTooLarge(Exception):
    """The saved document is over MAX_SIZE; fetching it again changes nothing."""


class SavedDocumentUnavailable(Exception):
    """The saved document cannot be read now, such as the editing service not answering; a later call can read it."""


@contextmanager
def saved_document(url):
    """The chunks of the saved document at the address a callback gave."""
    address = internal_saved_document_url(url)
    if not address:
        raise SavedDocumentRefused("The saved document's address is not on the editing service.")
    deadline = time.monotonic() + TOTAL_SECONDS
    try:
        response = requests.get(address, stream=True, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as error:
        raise SavedDocumentUnavailable(
            f"The editing service did not give the saved document: {type(error).__name__}."
        ) from None
    with response:
        if response.is_redirect or 300 <= response.status_code < 400:
            raise SavedDocumentRefused("The saved document's address redirects.")
        if response.status_code != 200:
            raise SavedDocumentUnavailable(
                f"The editing service answered {response.status_code} for the saved document."
            )
        length = response.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > MAX_SIZE:
            raise SavedDocumentTooLarge("The saved document is over 5 GiB.")
        yield _chunks(response, deadline)


def _chunks(response, deadline):
    size = 0
    try:
        for chunk in response.iter_content(CHUNK_SIZE):
            size += len(chunk)
            if size > MAX_SIZE:
                raise SavedDocumentTooLarge("The saved document is over 5 GiB.")
            if time.monotonic() > deadline:
                raise SavedDocumentUnavailable("Fetching the saved document took too long.")
            yield chunk
    except requests.RequestException as error:
        raise SavedDocumentUnavailable(f"The saved document stopped arriving: {type(error).__name__}.") from None

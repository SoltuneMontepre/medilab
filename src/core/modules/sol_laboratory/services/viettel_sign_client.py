"""Signing a hash with the laboratory's certificate through Viettel Sign's remote signing (MySign).

The account signs without confirmation in the MySign app, so a call returns the signature or fails. The secrets come
from the environment and are never logged.
"""

import base64
import logging
import os
import re
import unicodedata

import requests

_logger = logging.getLogger(__name__)

DEFAULT_URL = "https://remotesigning.viettel.vn"
URL = "VIETTEL_SIGN_URL"
CLIENT_ID = "VIETTEL_SIGN_CLIENT_ID"
CLIENT_SECRET = "VIETTEL_SIGN_CLIENT_SECRET"
PROFILE_ID = "VIETTEL_SIGN_PROFILE_ID"
USER_ID = "VIETTEL_SIGN_USER_ID"
TIMEOUT = 60
# Object identifiers of the hash Viettel Sign is given and of the signature it makes.
SHA256_OID = "2.16.840.1.101.3.4.2.1"
RSA_OID = "1.2.840.113549.1.1.1"
# Viettel Sign shows a document name of unaccented letters, digits, underscores, hyphens and spaces only.
NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_\- ]")
NAME_LENGTH = 60


class ViettelSignError(Exception):
    """Viettel Sign is not configured, cannot be reached or did not sign; a later attempt can still succeed."""


class ViettelSignClient:
    """One Viettel Sign account. Each call logs in again, since a signing is rare and a session lasts an hour."""

    def __init__(self, url, client_id, client_secret, profile_id, user_id):
        self.url = url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.profile_id = profile_id
        self.user_id = user_id

    def certificates(self):
        """The account's certificates as Viettel Sign reports them, each with its credential id, chain and status."""
        token = self._login()
        body = self._post(
            "/vtss/service/certificates/info",
            {**self._account(), "certificates": "chain", "certInfo": True, "authInfo": True},
            token,
        )
        if not isinstance(body, list):
            raise ViettelSignError("Viettel Sign returned no list of certificates")
        return body

    def sign_hash(self, credential_id, digest, document_name):
        """The RSA signature the certificate makes of a SHA-256 digest."""
        token = self._login()
        name = _document_name(document_name)
        body = self._post(
            "/vtss/service/signHash",
            {
                "credentialID": credential_id,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "numSignatures": 1,
                "documents": [{"document_id": name, "document_name": base64.b64encode(name.encode()).decode()}],
                "hash": [base64.b64encode(digest).decode()],
                "hashAlgo": SHA256_OID,
                "signAlgo": RSA_OID,
                "async": 0,
            },
            token,
        )
        signatures = body.get("signatures") if isinstance(body, dict) else None
        if not signatures:
            raise ViettelSignError("Viettel Sign returned no signature")
        return base64.b64decode(signatures[0])

    def _login(self):
        body = self._post("/vtss/service/ras/v1/login", self._account())
        token = body.get("access_token") if isinstance(body, dict) else None
        if not token:
            raise ViettelSignError("Viettel Sign returned no access token")
        return token

    def _account(self):
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "profile_id": self.profile_id,
            "user_id": self.user_id,
        }

    def _post(self, path, payload, token=None):
        # The one network call, so tests replace this method. The line names the call, never the secrets.
        _logger.info("Viettel Sign POST %s", path)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = requests.post(f"{self.url}{path}", json=payload, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise ViettelSignError(f"Viettel Sign could not be reached: {type(error).__name__}") from error
        try:
            body = response.json()
        except ValueError:
            body = None
        error = (body.get("error_description") or body.get("error")) if isinstance(body, dict) else None
        if response.status_code >= 400 or error:
            raise ViettelSignError(f"Viettel Sign {path} answered {response.status_code}: {error or 'no details'}")
        return body


def viettel_sign_client():
    """The client of the account set in the environment; refuses when a variable is missing."""
    values = [os.environ.get(name) for name in (CLIENT_ID, CLIENT_SECRET, PROFILE_ID, USER_ID)]
    if not all(values):
        raise ViettelSignError(
            f"Viettel Sign is not configured: set {CLIENT_ID}, {CLIENT_SECRET}, {PROFILE_ID} and {USER_ID}"
        )
    return ViettelSignClient(os.environ.get(URL) or DEFAULT_URL, *values)


def _document_name(name):
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return NAME_UNSAFE.sub("", ascii_name).strip()[:NAME_LENGTH] or "document"

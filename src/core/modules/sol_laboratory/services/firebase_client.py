"""Sending one push through Firebase Cloud Messaging HTTP v1.

OAuth tokens come from google-auth, which refreshes them. A device is turned off only when
Firebase names a permanent token failure. SMTP and FCM cannot promise exactly-once delivery:
a crash after the provider accepts and before this row is marked sent can send once more.
"""

import json
import logging
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from odoo.addons.sol_laboratory.constants.notifications import FIREBASE_CREDENTIALS, FIREBASE_PROJECT_ID

_logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
PERMANENT_TOKEN_CODES = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})
TIMEOUT = 30


class PermanentTokenError(Exception):
    """Firebase rejected this device token and it must not be used again."""


class TemporaryFirebaseError(Exception):
    """Firebase or the network failed in a way a later attempt can still succeed."""


class FirebaseClient:
    """One project. The access token is refreshed by google-auth when it expires."""

    def __init__(self, credentials, project_id):
        self.credentials = credentials
        self.project_id = project_id

    def send(self, token, title, body):
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        try:
            response = requests.post(
                f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send",
                headers={"Authorization": f"Bearer {self.credentials.token}"},
                json={"message": {"token": token, "notification": {"title": title, "body": body}}},
                timeout=TIMEOUT,
            )
        except requests.RequestException as error:
            _logger.info("Firebase push could not connect")
            raise TemporaryFirebaseError(str(error)) from error
        _logger.info("Firebase push HTTP %s", response.status_code)
        if response.status_code == 200:
            return
        self._raise_for_response(response)

    def _raise_for_response(self, response):
        error = _error_body(response)
        code = _error_code(error)
        status = str(error.get("status") or "")
        if _permanent_token_failure(code, status, str(error.get("message") or "")):
            raise PermanentTokenError(code or status)
        if response.status_code in {408, 429} or response.status_code >= 500:
            raise TemporaryFirebaseError(status or str(response.status_code))
        raise TemporaryFirebaseError(code or status or str(response.status_code))


def _error_body(response):
    try:
        payload = response.json()
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error")
    return error if isinstance(error, dict) else {}


def _error_code(error):
    for detail in error.get("details") or []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            return str(detail["errorCode"])
    return ""


def _permanent_token_failure(code, status, message):
    if code in PERMANENT_TOKEN_CODES or status in PERMANENT_TOKEN_CODES:
        return True
    invalid = code == "INVALID_ARGUMENT" or status == "INVALID_ARGUMENT"
    return invalid and "token" in message.lower()


def firebase_client_from_env():
    """A client when credentials exist. Nothing is logged from the credential JSON."""
    project_id = os.environ.get(FIREBASE_PROJECT_ID)
    raw = os.environ.get(FIREBASE_CREDENTIALS)
    if raw and project_id:
        try:
            info = json.loads(raw)
        except ValueError:
            _logger.error("Firebase credentials are not valid JSON")
            return None
        credentials = service_account.Credentials.from_service_account_info(info, scopes=[FCM_SCOPE])
        return FirebaseClient(credentials, project_id)
    try:
        import google.auth

        credentials, detected = google.auth.default(scopes=[FCM_SCOPE])
    except Exception:
        _logger.info("Firebase credentials are not set")
        return None
    project_id = project_id or detected
    if not credentials or not project_id:
        return None
    return FirebaseClient(credentials, project_id)

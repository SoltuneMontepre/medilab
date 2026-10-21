"""Signs the editor configuration and checks the calls of the editing service with the secret ONLYOFFICE Document Server
shares with Odoo. The secret comes from the environment only and is never logged or answered."""

import os
import time

import jwt

from odoo.addons.sol_laboratory.constants.laboratory_editing import JWT_SECRET_VARIABLE

ALGORITHM = "HS256"
# HS256 needs a secret at least as long as its hash.
MIN_SECRET_BYTES = 32
# Clock difference allowed between Odoo and the editing service, as the editing service allows.
LEEWAY_SECONDS = 60
# The prefix of the token in the editing service's header.
BEARER = "Bearer "
# Claims a token adds to the fields of the call it signs.
TOKEN_CLAIMS = ("iat", "exp", "nbf", "operation")
# The operation the editing service names in the tokens of its callbacks, from version 10.
CALLBACK_OPERATION = "callback"


class EditingCallbackRefused(Exception):
    """A call of the editing service that fails a check; nothing of it is stored."""


def jwt_secret():
    """The secret shared with the editing service, or None when it is not set or too short to sign with."""
    secret = os.environ.get(JWT_SECRET_VARIABLE) or ""
    return secret if len(secret.encode()) >= MIN_SECRET_BYTES else None


def sign(payload, secret, lifetime_seconds):
    """The token of the payload, valid for lifetime_seconds."""
    now = int(time.time())
    return jwt.encode({**payload, "iat": now, "exp": now + lifetime_seconds}, secret, algorithm=ALGORITHM)


def verify_callback(body, header, secret):
    """The fields of a callback once its tokens are checked: the token of its header, whose payload is the body, and
    the token of its body, whose claims are the body's fields. Either may come alone; every one that comes is checked,
    and the fields of the body must be those its tokens sign. Raises EditingCallbackRefused otherwise."""
    if not secret:
        raise EditingCallbackRefused("The editing service's secret is not set.")
    if not isinstance(body, dict):
        raise EditingCallbackRefused("The callback is not a JSON object.")
    signed = []
    if header:
        if not header.startswith(BEARER):
            raise EditingCallbackRefused("The token header is not a bearer token.")
        claims = _decode(header[len(BEARER) :], secret)
        payload = claims.get("payload")
        if not isinstance(payload, dict):
            raise EditingCallbackRefused("The header token has no payload.")
        _check_operation(claims, payload)
        signed.append(_fields(payload))
    if "token" in body:
        claims = _decode(body["token"], secret)
        _check_operation(claims)
        signed.append(_fields(claims))
    if not signed:
        raise EditingCallbackRefused("The callback has no token.")
    fields = signed[0]
    unsigned = _fields(body)
    if any(other != fields for other in signed[1:]) or (unsigned and unsigned != fields):
        raise EditingCallbackRefused("The callback's body is not what its tokens sign.")
    return fields


def _decode(token, secret):
    if not isinstance(token, str):
        raise EditingCallbackRefused("The token is not a string.")
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp"], "enforce_minimum_key_length": True},
            leeway=LEEWAY_SECONDS,
        )
    except jwt.InvalidTokenError as error:
        # The class names why without repeating the token.
        raise EditingCallbackRefused(f"The token is not valid: {type(error).__name__}.") from None


def _check_operation(*claims):
    if any(part.get("operation", CALLBACK_OPERATION) != CALLBACK_OPERATION for part in claims):
        raise EditingCallbackRefused("The token is not one of a callback.")


def _fields(payload):
    return {key: value for key, value in payload.items() if key not in (*TOKEN_CLAIMS, "token")}

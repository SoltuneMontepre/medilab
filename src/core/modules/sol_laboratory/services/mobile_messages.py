"""Messages Medilab Mobile reads and posts: in a conversation and in the chatter of a task, a sample or a test request,
with the person's rights."""

import base64

from odoo.api import Environment
from odoo.fields import Domain
from odoo.tools import plaintext2html

from odoo.addons.sol_laboratory.constants.laboratory_files import IDEMPOTENCY_CONFLICT, INVALID_REQUEST
from odoo.addons.sol_laboratory.constants.medilab_mobile import (
    FILE_MAX_BYTES,
    MESSAGE_PAGE_SIZE,
    PEOPLE_LIMIT,
    REQUEST_FILES_MAX_BYTES,
    TOO_LARGE,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MESSAGE,
    MODEL_RES_USERS,
    MODEL_SAMPLE,
    MODEL_TASK,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import not_found, readable

# The documents whose chatter the app shows.
CHATTER_MODELS = (MODEL_TASK, MODEL_SAMPLE, MODEL_TEST_REQUEST)
# The people a message may mention and a conversation may have: active internal users.
INTERNAL_USERS = Domain("share", "=", False)


def chatter_document(env: Environment, model: str, record_id: int):
    """The task, sample or test request the person may read; any other document is not found."""
    if model not in CHATTER_MODELS:
        raise not_found(env)
    return readable(env[model].browse(record_id))


def message_page(thread, before=None, after=None, limit=None):
    """A page of the messages people wrote in the thread, newest first, before or after a message."""
    messages = thread.env[MODEL_MAIL_MESSAGE]._message_fetch(
        Domain("message_type", "=", "comment"),
        thread=thread,
        before=int(before) if before else None,
        after=int(after) if after else None,
        limit=int(limit or MESSAGE_PAGE_SIZE),
    )["messages"]
    return {"messages": messages._mobile_values()}


def people(env: Environment, query: str):
    """The active people of the laboratory other than the person whose name matches, for conversations and mentions."""
    users = env[MODEL_RES_USERS].search(
        INTERNAL_USERS & Domain("id", "!=", env.uid) & Domain("name", "ilike", query or ""),
        order="name, id",
        limit=PEOPLE_LIMIT,
    )
    return {"people": [{"id": user.id, "name": user.name} for user in users]}


def internal_users(env: Environment, user_ids):
    """The active people of the laboratory of the ids; another id is refused."""
    ids = set(user_ids or [])
    users = env[MODEL_RES_USERS].search(INTERNAL_USERS & Domain("id", "in", list(ids)))
    if len(users) != len(ids):
        raise LaboratoryFileError(INVALID_REQUEST, env._("Choose only people of the laboratory."))
    return users


def post_from_phone(thread, device, body, key, **post_values):
    """Post the phone's text, mentions and files on the thread, as the web's composer does, once per Idempotency-Key: a
    request sent again answers the message the first one posted."""
    env = thread.env
    posted = env[MODEL_MAIL_MESSAGE]._created_with_key(device, key)
    if posted:
        if (posted.model, posted.res_id) != (thread._name, thread.id):
            raise LaboratoryFileError(
                IDEMPOTENCY_CONFLICT, env._("This Idempotency-Key was already sent with another request.")
            )
        return posted
    text = (body.get("text") or "").strip()
    files = decoded_files(env, body.get("files"))
    if not text and not files:
        raise LaboratoryFileError(INVALID_REQUEST, env._("Write a message or attach a file."))
    partners = internal_users(env, body.get("mentions")).partner_id
    # sudo: posting on a thread the person may post on, as the web's composer does.
    message = (
        thread.sudo()
        .with_context(mail_post_autofollow=False)
        .message_post(
            body=plaintext2html(text) if text else "",
            message_type="comment",
            partner_ids=partners.ids,
            attachments=files,
            **post_values,
        )
        .with_env(env)
    )
    message._keep_key(device, key)
    return message


def decoded_files(env: Environment, files):
    """The files of the request as message_post() takes them, once each is at most 10 MiB and all at most 25 MiB, which
    is checked on their encoded size before any is decoded."""
    total = sum(_decoded_size(file["data"]) for file in files or [])
    if total > REQUEST_FILES_MAX_BYTES:
        raise LaboratoryFileError(TOO_LARGE, env._("The files of one message are at most 25 MiB together."))
    decoded = []
    for file in files or []:
        if _decoded_size(file["data"]) > FILE_MAX_BYTES:
            raise LaboratoryFileError(TOO_LARGE, env._("%s is larger than 10 MiB.", file["name"]))
        try:
            content = base64.b64decode(file["data"], validate=True)
        except ValueError as error:
            raise LaboratoryFileError(INVALID_REQUEST, env._("%s is not sent as base64.", file["name"])) from error
        decoded.append((file["name"], content, {"mimetype": file.get("mimetype") or "application/octet-stream"}))
    return decoded


def _decoded_size(data: str) -> int:
    return len(data) * 3 // 4 - data[-2:].count("=")

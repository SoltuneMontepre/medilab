"""Run the deferred sol_demo seed once in the private Odoo service's PostgreSQL transaction."""

import hashlib
import json
import os
from datetime import UTC, datetime

from odoo import SUPERUSER_ID, api
from odoo.addons.sol_demo.bootstrap import (
    BOOTSTRAP_OWNER_VARIABLE,
    bootstrap_state,
    set_bootstrap_state,
)
from odoo.addons.sol_demo.hooks import seed_demo
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.pdf_signing import check_pdf

REPORT_URL_KEY = "report.url"
REPORT_URL = "http://odoo:8069"
LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"medilab.demo.bootstrap").digest()[:8], "big", signed=True
)


def _parameter(env, key):
    records = env["ir.config_parameter"].sudo()
    record = records.search([("key", "=", key)], limit=1)
    return (record.exists(), record.value if record else None)


def _restore_parameter(env, key, snapshot):
    records = env["ir.config_parameter"].sudo()
    original, value = snapshot
    current = records.search([("key", "=", key)], limit=1)
    if original:
        if current:
            current.value = value
        else:
            records.create({"key": key, "value": value})
    elif current:
        current.unlink()


def _verify_demo(env):
    quotations = env["medilab.quotation"].sudo().search([("order_id", "!=", False)])
    if any(
        not quotation.attachment_id
        or not bytes(quotation.attachment_id.raw).startswith(b"%PDF-")
        for quotation in quotations
    ):
        raise RuntimeError("A demo quotation is missing a valid PDF attachment")

    reports = env["medilab.test.report"].sudo().search([("status", "=", "issued")])
    if any(
        not report.attachment_id
        or not bytes(report.attachment_id.raw).startswith(b"%PDF-")
        for report in reports
    ):
        raise RuntimeError("An issued demo report is missing a valid PDF attachment")

    signatures = env["medilab.digital.signature"].sudo().search([])
    for signature in signatures:
        pdf = bytes(signature.attachment_id.raw)
        result = check_pdf(pdf)
        if (
            hashlib.sha256(pdf).hexdigest() != signature.file_hash
            or not result
            or not result.signature_valid
        ):
            raise RuntimeError(f"Demo digital signature {signature.id} did not verify")

    if not laboratory_bucket.is_ready():
        raise RuntimeError("The isolated Garage bucket is not reachable")
    contents = (
        env["medilab.laboratory.content"].sudo().search([("state", "=", "verified")])
    )
    for content in contents:
        digest = hashlib.sha256()
        size = 0
        with laboratory_bucket.read(content.object_key) as chunks:
            for chunk in chunks:
                digest.update(chunk)
                size += len(chunk)
        if size != content.size or digest.hexdigest() != content.sha256:
            raise RuntimeError(
                f"Demo bucket content {content.id} did not match its recorded hash"
            )

    uploads = (
        env["medilab.laboratory.upload"].sudo().search([("multipart_id", "!=", False)])
    )
    for upload in uploads:
        laboratory_bucket.uploaded_parts(
            upload.content_id.object_key, upload.multipart_id
        )
    return {
        "verified_bucket_objects": len(contents),
        "issued_reports": len(reports),
        "multipart_uploads": len(uploads),
        "quotations": len(quotations),
        "signatures": len(signatures),
    }


def run(env):
    owner = os.environ.get(BOOTSTRAP_OWNER_VARIABLE)
    env.cr.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])
    try:
        state = bootstrap_state(env)
        if not state or state.get("owner") != owner:
            raise RuntimeError(
                "Demo bootstrap ownership does not match this isolated attempt"
            )
        if state.get("status") == "completed":
            print("Demo bootstrap is already complete.")
            return
        if state.get("status") != "pending":
            raise RuntimeError(
                f"Demo bootstrap cannot run from state {state.get('status')!r}"
            )

        set_bootstrap_state(
            env,
            {
                "owner": owner,
                "started_at": datetime.now(UTC).isoformat(),
                "status": "running",
            },
        )
        env.cr.commit()

        report_url = _parameter(env, REPORT_URL_KEY)
        digital_signing = _parameter(env, DIGITAL_SIGNING_PARAMETER)
        try:
            env["ir.config_parameter"].sudo().set_str(REPORT_URL_KEY, REPORT_URL)
            env["ir.config_parameter"].sudo().set_bool(DIGITAL_SIGNING_PARAMETER, False)
            seed_demo(env)
            result = _verify_demo(env)
            _restore_parameter(env, DIGITAL_SIGNING_PARAMETER, digital_signing)
            _restore_parameter(env, REPORT_URL_KEY, report_url)
            for key, snapshot in (
                (DIGITAL_SIGNING_PARAMETER, digital_signing),
                (REPORT_URL_KEY, report_url),
            ):
                restored = _parameter(env, key)
                if bool(restored[0]) != bool(snapshot[0]) or restored[1] != snapshot[1]:
                    raise RuntimeError(
                        f"Temporary bootstrap configuration {key!r} was not restored"
                    )
            set_bootstrap_state(
                env,
                {
                    "seeded_at": datetime.now(UTC).isoformat(),
                    "owner": owner,
                    "status": "seeded",
                },
            )
            env.cr.commit()
        except BaseException as error:
            env.cr.rollback()
            failed_env = api.Environment(env.cr, SUPERUSER_ID, {})
            set_bootstrap_state(
                failed_env,
                {
                    "error": type(error).__name__,
                    "failed_at": datetime.now(UTC).isoformat(),
                    "owner": owner,
                    "status": "failed",
                },
            )
            env.cr.commit()
            raise
        print(json.dumps({**result, "status": "completed"}))
    finally:
        env.cr.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
        env.cr.commit()


odoo_env = locals()["env"]
run(odoo_env)

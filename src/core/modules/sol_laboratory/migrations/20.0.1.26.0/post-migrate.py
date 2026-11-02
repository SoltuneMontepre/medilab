import logging

from odoo.api import SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # Odoo leaves a new boolean column empty on existing rows; a test is accredited only once a scope line covers it.
    cr.execute("UPDATE medilab_sample_test SET is_accredited = FALSE WHERE is_accredited IS NULL")
    # A certificate listed only methods. Each method becomes a scope line that names no parameter or sample type, so it
    # accredits nothing a certificate does not state until an administrator completes it. Odoo drops the old links only
    # once every module is upgraded, so they are still there.
    cr.execute("SELECT to_regclass('medilab_accreditation_certificate_method_rel')")
    table = cr.fetchone()
    if not table or not table[0]:
        return
    cr.execute(
        """
        INSERT INTO medilab_accreditation_scope_line
               (certificate_id, method_id, to_confirm, create_uid, write_uid, create_date, write_date)
        SELECT link.certificate_id, link.method_id, TRUE, %(uid)s, %(uid)s,
               NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
          FROM medilab_accreditation_certificate_method_rel link
         WHERE NOT EXISTS (
               SELECT 1
                 FROM medilab_accreditation_scope_line line
                WHERE line.certificate_id = link.certificate_id AND line.method_id = link.method_id
         )
        """,
        {"uid": SUPERUSER_ID},
    )
    cr.execute(
        """
        SELECT certificate.code, method.code
          FROM medilab_accreditation_scope_line line
          JOIN medilab_accreditation_certificate certificate ON certificate.id = line.certificate_id
          JOIN medilab_testing_method method ON method.id = line.method_id
         WHERE line.to_confirm
         ORDER BY certificate.code, method.code
        """
    )
    lines = cr.fetchall()
    if lines:
        _logger.warning(
            "Scope lines an administrator must complete with their parameters and sample types: %s",
            "; ".join(f"{certificate} – {method}" for certificate, method in lines),
        )

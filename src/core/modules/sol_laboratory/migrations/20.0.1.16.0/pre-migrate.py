import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # Versions refer to verified content instead of holding a storage key of their own. Each SHA-256 that existing
    # versions have becomes one verified content under a new random key; their bytes were never stored in the bucket,
    # so reconciliation reports the object of each such content as missing.
    if not column_exists(cr, "medilab_laboratory_file_version", "storage_key"):
        return
    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS medilab_laboratory_content (
            id SERIAL PRIMARY KEY,
            object_key VARCHAR NOT NULL,
            state VARCHAR NOT NULL,
            size INT8,
            sha256 VARCHAR,
            create_uid INT4,
            create_date TIMESTAMP,
            write_uid INT4,
            write_date TIMESTAMP
        )
        """
    )
    cr.execute(
        """
        INSERT INTO medilab_laboratory_content (object_key, state, size, sha256, create_uid, create_date, write_uid,
                                                write_date)
        SELECT md5(gen_random_uuid()::text), 'verified', MIN(size), sha256, 1, now() AT TIME ZONE 'UTC', 1,
               now() AT TIME ZONE 'UTC'
          FROM medilab_laboratory_file_version
      GROUP BY sha256
        """
    )
    contents = cr.rowcount
    cr.execute("ALTER TABLE medilab_laboratory_file_version ADD COLUMN content_id INT4")
    cr.execute(
        """
        UPDATE medilab_laboratory_file_version version
           SET content_id = content.id
          FROM medilab_laboratory_content content
         WHERE content.sha256 = version.sha256
        """
    )
    versions = cr.rowcount
    cr.execute("ALTER TABLE medilab_laboratory_file_version DROP COLUMN storage_key")
    if contents:
        _logger.warning(
            "Recorded %s laboratory file contents as verified for %s versions; their bytes are not in the bucket.",
            contents,
            versions,
        )

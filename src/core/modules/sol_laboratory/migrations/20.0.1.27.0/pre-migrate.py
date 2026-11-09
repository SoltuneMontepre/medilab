import logging

from psycopg2 import sql

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # A limit now applies to one exact sample type. Each existing limit applied to the sample types its regulation
    # names, so it is copied to each of them, never to their narrower types. A regulation that names no sample type
    # applies to nothing, so its limits are removed.
    if column_exists(cr, "medilab_regulation_limit", "sample_type_id"):
        return
    cr.execute(
        "ALTER TABLE medilab_regulation_limit DROP CONSTRAINT IF EXISTS medilab_regulation_limit_regulation_parameter_unique"
    )
    cr.execute("ALTER TABLE medilab_regulation_limit ADD COLUMN sample_type_id INT4")
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'medilab_regulation_limit' AND column_name NOT IN ('id', 'sample_type_id')
        """
    )
    names = [name for (name,) in cr.fetchall()]
    cr.execute(
        """
        UPDATE medilab_regulation_limit limit_row
           SET sample_type_id = named.sample_type_id
          FROM (
                SELECT regulation_id, MIN(sample_type_id) AS sample_type_id
                  FROM medilab_regulation_sample_type_rel
              GROUP BY regulation_id
               ) named
         WHERE named.regulation_id = limit_row.regulation_id
        """
    )
    cr.execute(
        sql.SQL(
            """
            INSERT INTO medilab_regulation_limit ({columns}, sample_type_id)
            SELECT {copied}, named.sample_type_id
              FROM medilab_regulation_limit limit_row
              JOIN medilab_regulation_sample_type_rel named ON named.regulation_id = limit_row.regulation_id
             WHERE named.sample_type_id <> limit_row.sample_type_id
            """
        ).format(
            columns=sql.SQL(", ").join(sql.Identifier(name) for name in names),
            copied=sql.SQL(", ").join(sql.Identifier("limit_row", name) for name in names),
        )
    )
    copies = cr.rowcount
    cr.execute(
        """
        DELETE FROM medilab_regulation_limit limit_row
         USING medilab_regulation regulation
         WHERE regulation.id = limit_row.regulation_id AND limit_row.sample_type_id IS NULL
     RETURNING regulation.code, limit_row.parameter_id
        """
    )
    removed = cr.fetchall()
    if copies:
        _logger.info("Copied %s regulation limits to the other sample types their regulations name.", copies)
    if removed:
        _logger.warning(
            "Removed %s limits of regulations that name no sample type (regulation, parameter id): %s",
            len(removed),
            removed,
        )

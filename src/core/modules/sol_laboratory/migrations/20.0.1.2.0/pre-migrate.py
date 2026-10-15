from odoo.orm.registry import Registry


def migrate(cr, version):
    # The registry already decided there is no trigram support. Create the extension and say so before indexes.
    cr.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Registry(cr.dbname).has_trigram = True

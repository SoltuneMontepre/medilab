from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_SERVICE_PACKAGE


# A parameter price had one price; it becomes a period that applies from the day it was entered until further notice.
# A package had its own price; it now costs the sum of its parameters. Products take their names in every language.
def migrate(cr, _version):
    cr.execute(
        """
        INSERT INTO medilab_price_period
            (parameter_price_id, currency_id, list_price, valid_from, create_uid, create_date, write_uid, write_date)
        SELECT price.id, price.currency_id, price.list_price,
               (price.create_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
               price.create_uid, NOW() AT TIME ZONE 'UTC', price.write_uid, NOW() AT TIME ZONE 'UTC'
          FROM medilab_parameter_price price
         WHERE NOT EXISTS (SELECT 1 FROM medilab_price_period period WHERE period.parameter_price_id = price.id)
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    packages = env[MODEL_SERVICE_PACKAGE].with_context(active_test=False).search(Domain.TRUE)
    env.add_to_compute(packages._fields["list_price"], packages)
    packages._sync_catalog_product()
    env[MODEL_PARAMETER_PRICE].with_context(active_test=False).search(Domain.TRUE)._sync_catalog_product()

import logging

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_CHART_TEMPLATE,
    MODEL_PRODUCT_PRICELIST,
    MODEL_RES_COMPANY,
)
from odoo.addons.sol_commerce.constants.xml_ids import MAIN_COMPANY, VIETNAM, VND

_logger = logging.getLogger(__name__)

# The chart of accounts of l10n_vn.
VIETNAMESE_CHART = "vn"


def use_vietnamese_accounting(env):
    """Give the main company Vietnam, VND and the Vietnamese chart of accounts while it has no accounting yet.

    Odoo loads the chart of the company's country when `account` installs, and the generic chart in USD when the
    company has no country, which a new database's company does not.
    """
    company = env.ref(MAIN_COMPANY)
    if company.chart_template == VIETNAMESE_CHART:
        return
    if company.root_id._existing_accounting():
        _logger.warning(
            "%s keeps the %s chart in %s: it has journal items, so its chart and currency can no longer change.",
            company.name,
            company.chart_template,
            company.currency_id.name,
        )
        return
    vnd = env.ref(VND)
    company.write({"country_id": env.ref(VIETNAM).id, "currency_id": vnd.id})
    # Odoo loads a chart once the registry is ready. Installing `account` queued the generic chart there; this
    # replaces it.
    env.registry._auto_install_template = lambda ready: ready[MODEL_ACCOUNT_CHART_TEMPLATE].try_loading(
        VIETNAMESE_CHART, ready[MODEL_RES_COMPANY].browse(company.id)
    )
    env[MODEL_PRODUCT_PRICELIST].with_context(active_test=False).search(
        [("company_id", "in", [company.id, False]), ("currency_id", "!=", vnd.id)]
    ).currency_id = vnd

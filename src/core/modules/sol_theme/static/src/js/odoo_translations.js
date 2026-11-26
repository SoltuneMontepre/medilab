import { _t } from "@web/core/l10n/translation";

// Odoo 20 leaves these strings of its own screens without a Vietnamese translation. Naming them here exports them with
// this module, and the web client falls back to this module's translation when Odoo's own module has none.
_t("Save search");
_t("Filter name");
_t("Select one or several criteria");

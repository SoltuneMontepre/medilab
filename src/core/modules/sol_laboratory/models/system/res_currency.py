from typing import TYPE_CHECKING

from odoo import models, tools

from odoo.addons.base.models import res_currency
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CURRENCY

if TYPE_CHECKING:
    from medilab_model_types import Model_res_currency as ResCurrencyBase
else:
    ResCurrencyBase = object

# The unit Vietnamese invoices name; another currency keeps its translated label.
VIETNAMESE_UNITS = {"VND": "đồng"}
# The scales of the three groups of digits below a billion, from the highest.
VIETNAMESE_SCALES = ("triệu", "nghìn", "")
BILLION = 1_000_000_000


def vietnamese_number(number):
    """Read a whole number as Vietnamese invoices write it: 1,005,000 is "một triệu không trăm lẻ năm nghìn"."""
    billions, rest = divmod(number, BILLION)
    words = [vietnamese_number(billions), "tỷ"] if billions else []
    for scale, group in zip(VIETNAMESE_SCALES, (rest // 1_000_000, rest // 1_000 % 1_000, rest % 1_000)):
        if not group:
            continue
        # num2words reads a group alone, so it leaves out the zero hundreds and tens of a group after a higher one.
        if words and group < 100:
            words.append("không trăm lẻ" if group < 10 else "không trăm")
        words += [res_currency.num2words(group, lang="vi"), scale]
    return " ".join(word for word in words if word) or res_currency.num2words(0, lang="vi")


# Tiền Tệ: num2words has no Vietnamese currencies, which Odoo's amount in words needs, so a Vietnamese amount is read here.
class ResCurrency(models.Model, ResCurrencyBase):
    _inherit = MODEL_RES_CURRENCY

    def amount_to_text(self, amount):
        if res_currency.num2words is None or tools.get_lang(self.env).iso_code[:2] != "vi":
            return super().amount_to_text(amount)
        self.ensure_one()
        integral, _sep, fractional = f"{abs(amount):.{self.decimal_places}f}".partition(".")
        text = f"{vietnamese_number(int(integral))} {VIETNAMESE_UNITS.get(self.name, self.currency_unit_label)}"
        if int(fractional or 0):
            text = f"{text} và {vietnamese_number(int(fractional))} {self.currency_subunit_label}"
        if self.compare_amounts(amount, 0) < 0:
            text = f"âm {text}"
        return text[0].upper() + text[1:]

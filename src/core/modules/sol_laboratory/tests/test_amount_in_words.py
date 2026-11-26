from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAmountInWords(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vnd = cls.env.ref("base.VND").with_context(lang="vi_VN")
        cls.usd = cls.env.ref("base.USD").with_context(lang="vi_VN")

    def test_dong_amounts_read_as_vietnamese_invoices_write_them(self):
        cases = {
            0: "Không đồng",
            21: "Hai mươi mốt đồng",
            105: "Một trăm lẻ năm đồng",
            1_000: "Một nghìn đồng",
            1_010: "Một nghìn không trăm mười đồng",
            1_005_000: "Một triệu không trăm lẻ năm nghìn đồng",
            1_000_001: "Một triệu không trăm lẻ một đồng",
            1_230_000: "Một triệu hai trăm ba mươi nghìn đồng",
            363_000: "Ba trăm sáu mươi ba nghìn đồng",
            1_000_000_000: "Một tỷ đồng",
            2_000_000_000_000: "Hai nghìn tỷ đồng",
            -500_000: "Âm năm trăm nghìn đồng",
        }
        for amount, words in cases.items():
            with self.subTest(amount=amount):
                self.assertEqual(self.vnd.amount_to_text(amount), words)

    def test_another_currency_reads_its_subunits_with_its_own_names(self):
        unit, subunit = self.usd.currency_unit_label, self.usd.currency_subunit_label

        self.assertEqual(self.usd.amount_to_text(1_234), f"Một nghìn hai trăm ba mươi bốn {unit}")
        self.assertEqual(
            self.usd.amount_to_text(1_234.56), f"Một nghìn hai trăm ba mươi bốn {unit} và năm mươi sáu {subunit}"
        )
        self.assertEqual(self.usd.amount_to_text(21.05), f"Hai mươi mốt {unit} và năm {subunit}")

    def test_english_keeps_odoos_wording(self):
        vnd = self.vnd.with_context(lang="en_US")

        self.assertEqual(vnd.amount_to_text(1_005_000), "One Million, Five Thousand Dong")

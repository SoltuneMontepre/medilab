from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .request_case import RequestCase
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestLabCodes(RequestCase):
    def test_every_sample_gets_its_own_lab_code_from_the_yearly_sequence(self):
        other = self.create_request().sample_ids

        self.assertRegex(assert_instance(self.sample.code, str), r"^PTN\.\d{4}\.\d{4}$")
        self.assertRegex(assert_instance(self.request.code, str), r"^YC\.\d{4}\.\d{4}$")
        self.assertNotEqual(self.sample.code, other.code)

    def test_existing_lab_code_is_refused(self):
        other = self.create_request().sample_ids

        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.cr.savepoint():
            other.write({"code": self.sample.code})

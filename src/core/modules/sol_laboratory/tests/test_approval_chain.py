from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.approvals import (
    DECISION_REJECTED,
    DECISION_SIGNED,
    PURPOSE_CHANGE_REQUEST,
    PURPOSE_SIGNING,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_ROLE,
    MODEL_SIGNATURE,
)

DOCUMENT_MODEL = "qa.document"


@tagged("post_install", "-at_install")
class TestApprovalChain(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sales_role = cls.env[MODEL_ROLE].create({"code": "qa_sales", "name": "Sales"})
        cls.head_role = cls.env[MODEL_ROLE].create({"code": "qa_head", "name": "Head of Sales"})
        cls.chain = cls.env[MODEL_APPROVAL_CHAIN].create(
            {"document_model": DOCUMENT_MODEL, "purpose": PURPOSE_SIGNING, "name": "Signing"}
        )
        cls.sales_level = cls.create_level(cls.chain, 10, "Sales", cls.sales_role)
        cls.head_level = cls.create_level(cls.chain, 20, "Head of Sales", cls.head_role)
        cls.grant(cls.chemist, "signature.read.all")
        cls.grant(cls.microbiologist, "signature.read.all")

    @classmethod
    def create_level(cls, chain, sequence, name, role):
        return cls.env[MODEL_APPROVAL_LEVEL].create(
            {"chain_id": chain.id, "sequence": sequence, "name": name, "role_id": role.id}
        )

    @classmethod
    def sign(cls, person, level, decision=DECISION_SIGNED, reason=False, document_id=1):
        return cls.env[MODEL_SIGNATURE].create(
            {
                "document_model": DOCUMENT_MODEL,
                "document_id": document_id,
                "document_version": 1,
                "level_id": level.id,
                "signer_id": person.id,
                "signer_name": person.name,
                "signer_role": level.role_id.name,
                "level_name": level.name,
                "decision": decision,
                "reason": reason,
            }
        )

    def test_a_document_type_has_one_chain_per_purpose(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_APPROVAL_CHAIN].create(
                {"document_model": DOCUMENT_MODEL, "purpose": PURPOSE_SIGNING, "name": "Another"}
            )

        other = self.env[MODEL_APPROVAL_CHAIN].create(
            {"document_model": DOCUMENT_MODEL, "purpose": PURPOSE_CHANGE_REQUEST, "name": "Changes"}
        )

        self.assertTrue(other)

    def test_two_levels_cannot_share_a_position(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_level(self.chain, 10, "Duplicate", self.head_role)

    def test_a_rejection_needs_a_reason(self):
        with self.assertRaises(ValidationError):
            self.sign(self.chemist, self.head_level, DECISION_REJECTED)

        rejection = self.sign(self.chemist, self.head_level, DECISION_REJECTED, "Wrong price")

        self.assertEqual(rejection.reason, "Wrong price")

    def test_a_chain_with_a_signature_cannot_be_deleted_but_can_be_archived(self):
        self.sign(self.chemist, self.sales_level)

        with self.assertRaises(UserError) as refusal:
            self.chain.unlink()
        self.chain.action_archive()

        self.assertIn(self.chemist.name, str(refusal.exception))
        self.assertIn(self.sales_level.name, str(refusal.exception))
        self.assertFalse(self.chain.active)

    def test_a_chain_without_signatures_can_be_deleted(self):
        self.chain.unlink()

        self.assertFalse(self.chain.exists())

    def test_a_person_with_a_signature_cannot_be_deleted_but_can_be_archived(self):
        signature = self.sign(self.chemist, self.sales_level)

        with self.assertRaises(UserError) as refusal:
            self.chemist.unlink()
        self.chemist.action_archive()

        self.assertIn(signature.display_name, str(refusal.exception))
        self.assertFalse(self.chemist.active)

    def test_a_signature_is_withdrawn_from_the_highest_level_down(self):
        lower = self.sign(self.chemist, self.sales_level)
        higher = self.sign(self.microbiologist, self.head_level)

        with self.assertRaises(UserError):
            lower.with_user(self.chemist.user_id)._withdraw()
        higher.with_user(self.microbiologist.user_id)._withdraw()
        lower.with_user(self.chemist.user_id)._withdraw()

        self.assertTrue(higher.withdrawn_at)
        self.assertTrue(lower.withdrawn_at)

    def test_a_rejection_on_a_higher_level_is_withdrawn_first(self):
        lower = self.sign(self.chemist, self.sales_level)
        rejection = self.sign(self.microbiologist, self.head_level, DECISION_REJECTED, "Wrong price")

        with self.assertRaises(UserError):
            lower.with_user(self.chemist.user_id)._withdraw()
        rejection.with_user(self.microbiologist.user_id)._withdraw()
        lower.with_user(self.chemist.user_id)._withdraw()

        self.assertTrue(lower.withdrawn_at)

    def test_only_the_signer_withdraws_and_only_once(self):
        signature = self.sign(self.chemist, self.sales_level)

        with self.assertRaises(UserError):
            signature.with_user(self.microbiologist.user_id)._withdraw()
        signature.with_user(self.chemist.user_id)._withdraw()
        with self.assertRaises(UserError):
            signature.with_user(self.chemist.user_id)._withdraw()

    def test_a_signature_cannot_be_deleted(self):
        signature = self.sign(self.chemist, self.sales_level)

        with self.assertRaises(UserError):
            signature.unlink()

        self.assertTrue(signature.exists())

    def test_a_signature_of_a_completed_process_is_not_withdrawn(self):
        signature = self.sign(self.chemist, self.sales_level)

        with self.assertRaises(UserError):
            signature.with_user(self.chemist.user_id)._withdraw(process_completed=True)

        self.assertFalse(signature.withdrawn_at)

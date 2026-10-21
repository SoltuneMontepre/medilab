from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .audit_case import AuditLookup
from .laboratory_signing_case import MEMBER_PERMISSIONS, SIGNER_PERMISSIONS, LaboratorySigningCase
from odoo.addons.sol_laboratory.constants.approvals import (
    DECISION_REJECTED,
    DECISION_SIGNED,
    STATE_APPROVED,
    STATE_NONE,
    STATE_REJECTED,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import NOT_FOUND
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_VERSION, MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


@tagged("post_install", "-at_install")
class TestLaboratoryFileVersionSigning(AuditLookup, LaboratorySigningCase):
    def sign(self, version, person=None):
        self.as_person(version, person or self.head).action_sign()

    def test_signing_records_the_signer_the_version_and_its_hash(self):
        version = self.result_version()

        self.sign(version)

        signature = self.signatures(version)
        self.assertEqual(
            (signature.signer_id, signature.decision, signature.level_id),
            (self.head, DECISION_SIGNED, self.chain.level_ids),
        )
        self.assertEqual((signature.document_model, signature.document_id), (MODEL_LABORATORY_FILE_VERSION, version.id))
        self.assertEqual((signature.document_version, signature.document_hash), (1, version.sha256))
        self.assertEqual(version.approval_state, STATE_APPROVED)
        self.assertEqual(version.file_id.current_approval_state, STATE_APPROVED)

    def test_a_newer_version_of_the_file_shows_as_not_signed(self):
        signed = self.result_version()
        self.sign(signed)

        newer = self.result_version("lead 0.005 mg/L")

        self.assertEqual(newer.approval_state, STATE_NONE)
        self.assertEqual(newer.file_id.current_approval_state, STATE_NONE)
        self.assertFalse(self.signatures(newer))
        self.assertEqual(signed.approval_state, STATE_APPROVED)

    def test_only_the_current_version_of_a_file_is_signed(self):
        first = self.result_version()
        second = self.result_version("lead 0.005 mg/L")
        conflict = self.result_version("lead 0.006 mg/L", base_version=first)

        for version in (first, conflict):
            with self.subTest(number=version.number):
                self.assertFalse(self.as_person(version, self.head).approval_can_sign)
                with self.assertRaises(UserError):
                    self.sign(version)
        self.assertTrue(self.as_person(second, self.head).approval_can_sign)
        self.sign(second)
        self.assertEqual(second.approval_state, STATE_APPROVED)

    def test_only_versions_of_the_files_of_a_result_folder_are_signed(self):
        no_sample = self.env[MODEL_LABORATORY_FOLDER].create({"name": "Results", "owner_id": self.head.user_id.id})
        for folder in (self.raw_data, no_sample):
            version = self.save(self.file_of("run-01.csv", folder), "run 1", user=self.saver.user_id)
            with self.subTest(folder=folder.name), self.assertRaises(UserError):
                self.sign(version)
            self.assertEqual(version.approval_state, STATE_NONE)

    def test_the_signer_needs_the_folder_and_the_sample(self):
        version = self.result_version()
        outsider = self.create_person(
            "Do Van Long", self.department, "long.do", permissions=SIGNER_PERMISSIONS, roles=self.signer_role
        )
        with self.assertRaises(LaboratoryFileError) as refused:
            self.sign(version, outsider)
        self.assertEqual(refused.exception.code, NOT_FOUND)

        self.results.member_ids = [Command.create({"user_id": outsider.user_id.id})]
        outsider.permission_ids -= self.permissions("sample.read.all")
        with self.assertRaises((LaboratoryFileError, AccessError)):
            self.sign(version, outsider)
        self.assertFalse(self.signatures(version))

    def test_the_signer_needs_the_role_and_the_sign_permission(self):
        version = self.result_version()
        without_permission = self.create_person(
            "Vu Thi Mai", self.department, "mai.vu", permissions=MEMBER_PERMISSIONS, roles=self.signer_role
        )
        self.results.member_ids = [Command.create({"user_id": without_permission.user_id.id})]

        for person in (self.saver, without_permission):
            with self.subTest(person=person.name):
                self.assertFalse(self.as_person(version, person).approval_can_sign)
                with self.assertRaises((UserError, AccessError)):
                    self.sign(version, person)
        self.assertFalse(self.signatures(version))

    def test_rejecting_a_version_needs_a_reason(self):
        version = self.result_version()

        for reason in ("", "   "):
            with self.subTest(reason=reason), self.assertRaises(UserError):
                self.as_person(version, self.head).action_reject(reason)
        self.assertEqual(version.approval_state, STATE_NONE)

        self.as_person(version, self.head).action_reject("The calibration curve is missing.")

        rejection = self.signatures(version)
        self.assertEqual(
            (rejection.decision, rejection.reason), (DECISION_REJECTED, "The calibration curve is missing.")
        )
        self.assertEqual(rejection.document_hash, version.sha256)
        self.assertEqual(version.approval_state, STATE_REJECTED)

    def test_withdrawing_the_signature_lets_the_version_be_signed_again(self):
        version = self.result_version()
        self.sign(version)

        self.as_person(version, self.head).action_withdraw()

        self.assertEqual(version.approval_state, STATE_NONE)
        self.sign(version)
        withdrawn, standing = self.signatures(version)
        self.assertTrue(withdrawn.withdrawn_at)
        self.assertEqual((standing.document_version, standing.document_hash), (2, version.sha256))
        self.assertEqual(version.approval_state, STATE_APPROVED)

    def test_a_signer_who_no_longer_reads_the_file_cannot_withdraw(self):
        def leave_folder(person):
            self.results.member_ids.filtered(lambda member: member.user_id == person.user_id).unlink()

        def lose_sample(person):
            person.permission_ids -= self.permissions("sample.read.all")

        cases = (
            ("left the folder", leave_folder, ()),
            ("lost the sample", lose_sample, ()),
            ("reads every version but left the folder", leave_folder, ("laboratory_file_version.read.all",)),
        )
        for index, (case, lose_access, extra_permissions) in enumerate(cases):
            with self.subTest(case=case):
                signer = self.create_person(
                    f"Signer {index}",
                    self.department,
                    f"file.signer.{index}",
                    permissions=(*SIGNER_PERMISSIONS, *extra_permissions),
                    roles=self.signer_role,
                )
                self.results.member_ids = [Command.create({"user_id": signer.user_id.id})]
                version = self.result_version(f"lead 0.00{index} mg/L", f"lead-{index}.xlsx")
                self.sign(version, signer)

                lose_access(signer)

                if extra_permissions:
                    self.assertFalse(self.as_person(version, signer).approval_can_withdraw)
                with self.assertRaises(LaboratoryFileError) as refused:
                    self.as_person(version, signer).action_withdraw()
                self.assertEqual(refused.exception.code, NOT_FOUND)
                self.assertFalse(self.signatures(version).withdrawn_at)
                self.assertRecordValues(version, [{"approval_state": STATE_APPROVED, "document_version": 1}])

    def test_the_signing_state_changes_only_by_signing(self):
        version = self.result_version()

        for user in (self.env.ref("base.user_admin"), self.head.user_id):
            with self.subTest(user=user.login), self.assertRaises(UserError):
                version.with_user(user).write({"approval_state": STATE_APPROVED})
        self.assertEqual(version.approval_state, STATE_NONE)

    def test_a_signed_version_keeps_its_content_and_its_signing_round(self):
        version = self.result_version()
        self.sign(version)

        for vals in ({"sha256": self.sha("other")}, {"document_version": 2}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                version.write(vals)

    def test_signing_does_not_change_when_the_file_was_last_saved(self):
        version = self.result_version()
        file = version.file_id
        file.invalidate_recordset(["write_date"])
        last_saved = file.write_date

        self.sign(version)

        file.invalidate_recordset(["write_date"])
        self.assertEqual(file.write_date, last_saved)

    def test_signing_and_rejecting_are_recorded_in_the_audit_trail(self):
        signed = self.result_version()
        self.sign(signed)
        rejected = self.result_version("lead 0.005 mg/L")
        self.as_person(rejected, self.head).action_reject("The blank is above the limit of detection.")

        self.assertLessEqual({"sign", "approve"}, set(self.entries(signed).mapped("action")))
        self.assertEqual(self.entries(signed, "sign").user_id, self.head.user_id)
        self.assertIn("The blank is above the limit of detection.", self.entries(rejected, "reject").note)

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, RESTORED, VERIFIED


@tagged("post_install", "-at_install")
class TestLaboratoryFileDemo(TransactionCase):
    def test_the_hplc_results_have_five_versions_from_two_computers_one_of_them_restored(self):
        results = self.env.ref("sol_demo.demo_laboratory_file_hplc_results")
        versions = results.version_ids.sorted("number")

        self.assertEqual(versions.mapped("number"), [1, 2, 3, 4, 5])
        self.assertEqual(len(versions.device_id), 2)
        self.assertEqual(versions[3].source, CONFLICT)
        restored = versions[4]
        self.assertEqual((restored.source, restored.restored_from_id), (RESTORED, versions[0]))
        self.assertEqual(results.current_version_id, restored)

    def test_versions_share_stored_content(self):
        results = self.env.ref("sol_demo.demo_laboratory_file_hplc_results").version_ids.sorted("number")
        run = self.env.ref("sol_demo.demo_laboratory_file_aas_run").current_version_id
        copy = self.env.ref("sol_demo.demo_laboratory_file_hplc_run_copy").current_version_id

        self.assertEqual(results[4].content_id, results[0].content_id)
        self.assertEqual(copy.content_id, run.content_id)
        self.assertNotEqual(copy.file_id.folder_id, run.file_id.folder_id)
        self.assertEqual(run.content_id.sudo().state, VERIFIED)

    def test_seeding_again_adds_nothing(self):
        from odoo.addons.sol_demo.demo_laboratory_files import seed_laboratory_file_restores

        results = self.env.ref("sol_demo.demo_laboratory_file_hplc_results")

        seed_laboratory_file_restores(self.env)

        self.assertEqual(len(results.version_ids), 5)

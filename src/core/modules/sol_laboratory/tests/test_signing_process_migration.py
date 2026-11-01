from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE, MODEL_SIGNING_PROCESS

END_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.25.0" / "end-migrate.py"


@tagged("post_install", "-at_install")
class TestSigningProcessMigration(ResultCase):
    def processes(self, document):
        return self.env[MODEL_SIGNING_PROCESS].search(
            [("document_model", "=", document._name), ("document_id", "=", document.id)]
        )

    def test_upgrade_starts_signed_documents_and_skips_document_types_no_longer_signed(self):
        result = self.enter()
        self.send(result)
        signature = self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", result._name), ("document_id", "=", result.id)]
        )
        # Before the upgrade no document had a process, and a type that is no longer signed kept its signatures.
        self.env.cr.execute(
            "DELETE FROM medilab_signing_process WHERE document_model = %s AND document_id = %s",
            [result._name, result.id],
        )
        self.env.cr.execute(
            "CREATE TEMP TABLE signature_copy AS SELECT * FROM medilab_signature WHERE id = %s", [signature.id]
        )
        self.env.cr.execute(
            """
            UPDATE signature_copy SET id = nextval('medilab_signature_id_seq'), document_model = 'res.partner',
                   document_id = %s
            """,
            [self.env.user.partner_id.id],
        )
        self.env.cr.execute("INSERT INTO medilab_signature SELECT * FROM signature_copy")
        self.env.cr.execute("DROP TABLE signature_copy")
        self.env.invalidate_all()

        load_script(str(END_MIGRATE), "end_migrate").migrate(self.env.cr, "20.0.1.21.0")

        self.assertTrue(self.processes(result))
        self.assertFalse(self.processes(self.env.user.partner_id))

import importlib.util
from pathlib import Path

from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SUBCONTRACTOR

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.6.0"
SNAPSHOT = "medilab_is_accredited_upgrade_snapshot"
SNAPSHOT_MARKER = "medilab_is_accredited_upgrade_snapshot_done"


def _load_migrate(name):
    path = MIGRATIONS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.migrate


def _drop_snapshot(cr):
    cr.execute(f"DROP TABLE IF EXISTS {SNAPSHOT}")
    cr.execute(f"DROP TABLE IF EXISTS {SNAPSHOT_MARKER}")


@tagged("post_install", "-at_install")
class TestAccreditationMigration(MasterDataCase):
    """Exercises pre/post migrate scripts on a populated cursor (upgrade-from-1.5.0 behaviour)."""

    def test_snapshot_recompute_for_true_false_and_subcontracted(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create({"name": "Migration Sub"})
        subcontracted = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "subcontractor_id": subcontractor.id,
            }
        )
        self.env.cr.execute(
            """
            UPDATE medilab_parameter_method
               SET is_accredited = (id IN %s)
            """,
            [(self.pair.id, subcontracted.id)],
        )
        self.env.invalidate_all()
        _drop_snapshot(self.env.cr)
        _load_migrate("pre-migrate")(self.env.cr, "20.0.1.5.0")
        _load_migrate("post-migrate")(self.env.cr, "20.0.1.5.0")
        self.pair.invalidate_recordset(["is_accredited"])
        subcontracted.invalidate_recordset(["is_accredited"])
        self.assertFalse(self.pair.is_accredited)
        self.assertFalse(subcontracted.is_accredited)
        self.env.cr.execute(f"SELECT COUNT(*) FROM {SNAPSHOT}")
        count = self.env.cr.fetchone()
        assert count is not None
        self.assertGreater(count[0], 0)
        self.env.cr.execute(f"SELECT old_value FROM {SNAPSHOT} WHERE pair_id = %s", [self.pair.id])
        old_row = self.env.cr.fetchone()
        assert old_row is not None
        self.assertTrue(old_row[0])

    def test_pre_migrate_is_retry_safe(self):
        pre = _load_migrate("pre-migrate")
        _drop_snapshot(self.env.cr)
        pre(self.env.cr, "20.0.1.5.0")
        self.env.cr.execute(f"SELECT pair_id, old_value FROM {SNAPSHOT} ORDER BY pair_id")
        first = self.env.cr.fetchall()
        self.env.cr.execute(
            "UPDATE medilab_parameter_method SET is_accredited = NOT COALESCE(is_accredited, FALSE) WHERE id = %s",
            [self.pair.id],
        )
        pre(self.env.cr, "20.0.1.5.0")
        self.env.cr.execute(f"SELECT pair_id, old_value FROM {SNAPSHOT} ORDER BY pair_id")
        self.assertEqual(first, self.env.cr.fetchall())

    def test_pre_migrate_empty_table_marker_is_idempotent(self):
        """Zero pairs still leave a completion marker so a rerun does not resnapshot."""
        with self.env.cr.savepoint() as sp:
            self.env.cr.execute("DELETE FROM medilab_parameter_method")
            _drop_snapshot(self.env.cr)
            pre = _load_migrate("pre-migrate")
            pre(self.env.cr, "20.0.1.5.0")
            self.env.cr.execute(f"SELECT COUNT(*) FROM {SNAPSHOT}")
            row = self.env.cr.fetchone()
            assert row is not None
            self.assertEqual(row[0], 0)
            self.env.cr.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s",
                [SNAPSHOT_MARKER],
            )
            row = self.env.cr.fetchone()
            assert row is not None
            self.assertEqual(row[0], 1)
            self.env.cr.execute(
                """
                INSERT INTO medilab_parameter_method
                    (parameter_id, method_id, unit_id, department_id, is_accredited, active)
                VALUES (%s, %s, %s, %s, TRUE, TRUE)
                """,
                [self.parameter.id, self.method.id, self.unit.id, self.department.id],
            )
            pre(self.env.cr, "20.0.1.5.0")
            self.env.cr.execute(f"SELECT COUNT(*) FROM {SNAPSHOT}")
            row = self.env.cr.fetchone()
            assert row is not None
            self.assertEqual(row[0], 0)
            sp.close(rollback=True)

    def test_empty_parameter_method_table_is_safe(self):
        with self.env.cr.savepoint() as sp:
            self.env.cr.execute("DELETE FROM medilab_parameter_method")
            _drop_snapshot(self.env.cr)
            _load_migrate("pre-migrate")(self.env.cr, "20.0.1.5.0")
            _load_migrate("post-migrate")(self.env.cr, "20.0.1.5.0")
            self.env.cr.execute(f"SELECT COUNT(*) FROM {SNAPSHOT}")
            row = self.env.cr.fetchone()
            assert row is not None
            self.assertEqual(row[0], 0)
            sp.close(rollback=True)

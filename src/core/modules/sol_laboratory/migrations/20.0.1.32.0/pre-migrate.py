def migrate(cr, _version):
    # Results now copy the way of testing, sample type, LOD, LOQ and regulation they are entered with. Filling the
    # columns before the upgrade keeps Odoo from computing them, which would also recompute and rewrite the unit and
    # limit copied before. A database older than 20.0.1.24.0 gets the applicability table only after this script, so
    # Odoo computes the columns there.
    cr.execute("SELECT to_regclass('medilab_parameter_method_sample_type')")
    if not cr.fetchone()[0]:
        return
    cr.execute(
        """
        ALTER TABLE medilab_test_result
            ADD COLUMN IF NOT EXISTS parameter_method_id integer,
            ADD COLUMN IF NOT EXISTS sample_type_id integer,
            ADD COLUMN IF NOT EXISTS lod numeric,
            ADD COLUMN IF NOT EXISTS loq numeric,
            ADD COLUMN IF NOT EXISTS regulation_id integer,
            ADD COLUMN IF NOT EXISTS comparison_requested boolean
        """
    )
    cr.execute(
        """
        UPDATE medilab_test_result result
           SET sample_type_id = sample.sample_type_id,
               regulation_id = sample.regulation_id,
               parameter_method_id = COALESCE(
                   test.parameter_method_id,
                   (SELECT way.parameter_method_id
                      FROM medilab_parameter_method_sample_type way
                     WHERE way.parameter_id = test.parameter_id
                       AND way.sample_type_id = sample.sample_type_id
                       AND way.is_default)
               ),
               comparison_requested = EXISTS (
                   SELECT 1
                     FROM medilab_regulation_limit limit_row
                    WHERE limit_row.regulation_id = sample.regulation_id
                      AND limit_row.parameter_id = test.parameter_id
               )
          FROM medilab_sample_test test
          JOIN medilab_sample sample ON sample.id = test.sample_id
         WHERE test.id = result.sample_test_id
        """
    )
    cr.execute(
        """
        UPDATE medilab_test_result result
           SET lod = way.lod, loq = way.loq
          FROM medilab_parameter_method_sample_type way
         WHERE way.parameter_method_id = result.parameter_method_id
           AND way.sample_type_id = result.sample_type_id
        """
    )

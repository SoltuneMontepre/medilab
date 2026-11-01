import logging

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tools.sql import column_exists

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD_SAMPLE_TYPE, MODEL_TEST_PARAMETER

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # The unit, detection limits, decimals and default moved from the way of testing to each sample type it applies to.
    # Only the default way is known to apply to the sample types its parameter listed, so only it gets them; every
    # other way waits for an administrator, and the log keeps what it had so nothing is lost. A limit of 0 was how an
    # empty limit was saved, so it becomes empty, and limits that were never valid are left empty and logged.
    if not column_exists(cr, "medilab_parameter_method", "is_default"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        SELECT way.id, way.parameter_id, way.unit_id, NULLIF(way.lod, 0), NULLIF(way.loq, 0), way.result_decimals,
               rel.sample_type_id
          FROM medilab_parameter_method way
          JOIN medilab_test_parameter_sample_type_rel rel ON rel.parameter_id = way.parameter_id
         WHERE way.is_default AND way.active
        """
    )
    vals_list, invalid = [], {}
    for way_id, parameter_id, unit_id, lod, loq, result_decimals, sample_type_id in cr.fetchall():
        if _invalid(lod, loq):
            invalid[way_id] = (lod, loq)
            lod = loq = None
        vals_list.append(
            {
                "parameter_id": parameter_id,
                "parameter_method_id": way_id,
                "sample_type_id": sample_type_id,
                "unit_id": unit_id,
                "lod": lod,
                "loq": loq,
                "result_decimals": result_decimals or 0,
                "is_default": True,
            }
        )
    env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE].create(vals_list)
    for way_id, (lod, loq) in sorted(invalid.items()):
        _logger.warning(
            "Way of testing %s had LOD %s and LOQ %s, which are not valid limits, so its sample types have none: enter "
            "them again.",
            way_id,
            lod,
            loq,
        )
    cr.execute(
        """
        SELECT way.id, way.parameter_id, parameter.name->>'en_US', method.code, unit.name, way.lod, way.loq,
               way.result_decimals
          FROM medilab_parameter_method way
          JOIN medilab_test_parameter parameter ON parameter.id = way.parameter_id
          JOIN medilab_testing_method method ON method.id = way.method_id
          LEFT JOIN medilab_measurement_unit unit ON unit.id = way.unit_id
         WHERE way.active
           AND NOT EXISTS (SELECT 1 FROM medilab_parameter_method_sample_type a WHERE a.parameter_method_id = way.id)
         ORDER BY way.parameter_id, way.id
        """
    )
    for way_id, parameter_id, parameter, method, unit, lod, loq, result_decimals in cr.fetchall():
        _logger.warning(
            "Way of testing %s (%s) of parameter %s (%s) applies to no sample type: add its sample types. Before the "
            "upgrade it had unit %s, LOD %s, LOQ %s and %s decimals.",
            way_id,
            method,
            parameter_id,
            parameter,
            unit,
            lod,
            loq,
            result_decimals,
        )
    cr.execute(
        """
        SELECT rel.parameter_id, parameter.name->>'en_US', string_agg(sample_type.name->>'en_US', ', ' ORDER BY sample_type.name->>'en_US')
          FROM medilab_test_parameter_sample_type_rel rel
          JOIN medilab_test_parameter parameter ON parameter.id = rel.parameter_id
          JOIN medilab_sample_type sample_type ON sample_type.id = rel.sample_type_id
         WHERE NOT EXISTS (
               SELECT 1 FROM medilab_parameter_method way WHERE way.parameter_id = rel.parameter_id AND way.is_default
           )
         GROUP BY rel.parameter_id, parameter.name
         ORDER BY rel.parameter_id
        """
    )
    for parameter_id, parameter, sample_types in cr.fetchall():
        _logger.warning(
            "Parameter %s (%s) had no default way of testing, so it is no longer offered on %s: add them to its ways of "
            "testing.",
            parameter_id,
            parameter,
            sample_types,
        )
    parameters = env[MODEL_TEST_PARAMETER].with_context(active_test=False).search([])
    env.add_to_compute(parameters._fields["sample_type_ids"], parameters)
    parameters.flush_recordset(["sample_type_ids"])
    cr.execute(
        """
        SELECT test.parameter_method_id, sample.sample_type_id, count(*)
          FROM medilab_sample_test test
          JOIN medilab_sample sample ON sample.id = test.sample_id
         WHERE test.parameter_method_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM medilab_parameter_method_sample_type a
                WHERE a.parameter_method_id = test.parameter_method_id AND a.sample_type_id = sample.sample_type_id
           )
         GROUP BY 1, 2
         ORDER BY 1, 2
        """
    )
    for way_id, sample_type_id, count in cr.fetchall():
        _logger.warning(
            "%s sample tests use way of testing %s on sample type %s, which it does not apply to yet: add that sample "
            "type to the way, or their results have no unit.",
            count,
            way_id,
            sample_type_id,
        )
    cr.execute(
        """
        ALTER TABLE medilab_parameter_method
            DROP COLUMN IF EXISTS unit_id,
            DROP COLUMN IF EXISTS lod,
            DROP COLUMN IF EXISTS loq,
            DROP COLUMN IF EXISTS result_decimals,
            DROP COLUMN IF EXISTS is_default
        """
    )


def _invalid(lod, loq):
    return (lod is not None and lod < 0) or (loq is not None and loq < 0) or (None not in (lod, loq) and lod > loq)

import logging

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tools.sql import column_exists

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD_SAMPLE_TYPE, MODEL_TEST_PARAMETER

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # The unit, detection limits, decimals and default moved from the way of testing to each sample type it applies to.
    # Only the default way is known to apply to the sample types its parameter listed, so only it gets them; every
    # other way waits for an administrator. A limit of 0 was how an empty limit was saved, so it becomes empty.
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
    vals_list = [
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
        for way_id, parameter_id, unit_id, lod, loq, result_decimals, sample_type_id in cr.fetchall()
    ]
    env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE].create(vals_list)
    cr.execute(
        """
        SELECT way.id, way.parameter_id
          FROM medilab_parameter_method way
         WHERE way.active
           AND NOT EXISTS (SELECT 1 FROM medilab_parameter_method_sample_type a WHERE a.parameter_method_id = way.id)
         ORDER BY way.parameter_id, way.id
        """
    )
    for way_id, parameter_id in cr.fetchall():
        _logger.warning(
            "Way of testing %s of parameter %s applies to no sample type: add its sample types with their unit and "
            "detection limits.",
            way_id,
            parameter_id,
        )
    cr.execute(
        """
        SELECT DISTINCT rel.parameter_id
          FROM medilab_test_parameter_sample_type_rel rel
         WHERE NOT EXISTS (
               SELECT 1 FROM medilab_parameter_method way WHERE way.parameter_id = rel.parameter_id AND way.is_default
           )
         ORDER BY rel.parameter_id
        """
    )
    for (parameter_id,) in cr.fetchall():
        _logger.warning(
            "Parameter %s had no default way of testing, so it is no longer offered on its sample types: add them to "
            "its ways of testing.",
            parameter_id,
        )
    parameters = env[MODEL_TEST_PARAMETER].with_context(active_test=False).search([])
    env.add_to_compute(parameters._fields["sample_type_ids"], parameters)
    parameters.flush_recordset(["sample_type_ids"])
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

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    cr.execute("SELECT to_regclass('medilab_parameter_method_machine')")
    if cr.fetchone()[0]:
        _link_machines_to_methods(cr)
    # An in-house way whose method has no machine needs its own duration before it can be booked.
    cr.execute(
        """
        SELECT way.id, parameter.name->>'en_US', method.code
          FROM medilab_parameter_method way
          JOIN medilab_test_parameter parameter ON parameter.id = way.parameter_id
          JOIN medilab_testing_method method ON method.id = way.method_id
         WHERE way.department_id IS NOT NULL AND way.active AND way.duration_minutes IS NULL
           AND NOT EXISTS (SELECT 1 FROM medilab_machine_method link WHERE link.method_id = way.method_id)
         ORDER BY way.id
        """
    )
    for way_id, parameter, method in cr.fetchall():
        _logger.warning(
            "Way of testing %s (%s by %s) has no machine and no duration; it cannot be booked until it has one.",
            way_id,
            parameter,
            method,
        )
    # Each booking keeps the testing method of its sample test's way, which shared intervals compare.
    cr.execute(
        """
        UPDATE medilab_machine_booking booking
           SET method_id = way.method_id
          FROM medilab_sample_test test
          JOIN medilab_parameter_method way ON way.id = test.parameter_method_id
         WHERE test.id = booking.sample_test_id AND booking.method_id IS NULL
        """
    )


def _link_machines_to_methods(cr):
    """One machine-and-method link for each machine and method of the way-and-machine links, with capacity 1 and the
    longest run time of those links, which is logged when they differ."""
    cr.execute(
        """
        SELECT link.machine_id, machine.code, way.method_id, method.code,
               min(link.run_minutes), max(link.run_minutes)
          FROM medilab_parameter_method_machine link
          JOIN medilab_parameter_method way ON way.id = link.parameter_method_id
          JOIN medilab_machine machine ON machine.id = link.machine_id
          JOIN medilab_testing_method method ON method.id = way.method_id
         GROUP BY link.machine_id, machine.code, way.method_id, method.code
         ORDER BY machine.code, method.code
        """
    )
    for machine_id, machine, method_id, method, shortest, longest in cr.fetchall():
        cr.execute(
            """
            INSERT INTO medilab_machine_method
                   (machine_id, method_id, duration_minutes, capacity, create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s, 1, 1, now() at time zone 'utc', 1, now() at time zone 'utc')
            ON CONFLICT (machine_id, method_id) DO NOTHING
            """,
            (machine_id, method_id, longest),
        )
        if shortest != longest:
            _logger.warning(
                "%s ran the ways of testing of %s in %s to %s minutes; its link takes the longest. Check it.",
                machine,
                method,
                shortest,
                longest,
            )
    # The accesses of the moved permissions follow them to the new model.
    cr.execute(
        """
        UPDATE ir_access access
           SET model_id = new_model.id
          FROM ir_model old_model, ir_model new_model
         WHERE old_model.model = 'medilab.parameter.method.machine' AND new_model.model = 'medilab.machine.method'
           AND access.model_id = old_model.id AND access.name LIKE 'Permission: %'
        """
    )
    # Odoo forgets the removed model but keeps its table.
    cr.execute("DROP TABLE medilab_parameter_method_machine")

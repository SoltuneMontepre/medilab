OLD_PREFIXES = [
    ("medilab.unit.category", "unit_category_"),
    ("medilab.measurement.unit", "unit_"),
    ("res.partner", "partner_"),
    ("res.partner", "demo_partner_"),
    ("medilab.subcontractor", "subcontractor_"),
    ("medilab.sample.type", "sample_type_"),
    ("medilab.parameter.group", "group_"),
    ("medilab.testing.field", "field_"),
    ("medilab.testing.method", "method_"),
    ("medilab.test.parameter", "parameter_"),
    ("medilab.parameter.method", "parameter_method_"),
    ("medilab.regulation", "regulation_"),
    ("medilab.regulation.limit", "regulation_limit_"),
    ("medilab.quality.registration", "quality_registration_"),
    ("medilab.machine", "machine_"),
    ("medilab.machine.service", "machine_service_"),
    ("medilab.parameter.method.machine", "machine_run_"),
    ("medilab.chemical", "chemical_"),
    ("medilab.notification.event.recipient", "demo_notification_recipient_"),
]


def migrate(cr, _version):
    # The demo records are named demo_<model>_<short name>, as the demo data convention says.
    for model, old_prefix in OLD_PREFIXES:
        new_prefix = f"demo_{model.removeprefix('medilab.').replace('.', '_')}_"
        cr.execute(
            "UPDATE ir_model_data SET name = %s || substr(name, %s) "
            "WHERE module = 'sol_demo' AND model = %s AND starts_with(name, %s)",
            (new_prefix, len(old_prefix) + 1, model, old_prefix),
        )

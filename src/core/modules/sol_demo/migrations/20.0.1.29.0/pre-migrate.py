LINKS = {
    "demo_machine_method_aas_lead": ("demo_machine_aas", "demo_testing_method_tcvn_7602"),
    "demo_machine_method_aas_2_lead": ("demo_machine_aas_2", "demo_testing_method_tcvn_7602"),
    "demo_machine_method_aas_3_lead": ("demo_machine_aas_3", "demo_testing_method_tcvn_7602"),
    "demo_machine_method_icpms_metals": ("demo_machine_icpms", "demo_testing_method_iso_17294_2"),
    "demo_machine_method_incubator_coliforms": ("demo_machine_incubator", "demo_testing_method_tcvn_6187_2"),
    "demo_machine_method_incubator_e_coli": ("demo_machine_incubator", "demo_testing_method_tcvn_6187_1"),
    "demo_machine_method_incubator_2_coliforms": ("demo_machine_incubator_2", "demo_testing_method_tcvn_6187_2"),
    "demo_machine_method_incubator_2_e_coli": ("demo_machine_incubator_2", "demo_testing_method_tcvn_6187_1"),
    "demo_machine_method_uvvis_chromium_vi": ("demo_machine_uvvis", "demo_testing_method_chromium_vi_colorimetry"),
}


def migrate(cr, _version):
    # The laboratory's upgrade turned the way-and-machine links into machine-and-method links. Those of the demo
    # machines and methods take the ids of their demo records, so the demo does not link them a second time.
    for name, (machine, method) in LINKS.items():
        cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            SELECT 'sol_demo', %s, 'medilab.machine.method', link.id, TRUE
              FROM medilab_machine_method link
              JOIN ir_model_data machine
                ON machine.module = 'sol_demo' AND machine.name = %s AND machine.res_id = link.machine_id
              JOIN ir_model_data method
                ON method.module = 'sol_demo' AND method.name = %s AND method.res_id = link.method_id
            ON CONFLICT (module, name) DO NOTHING
            """,
            (name, machine, method),
        )
    cr.execute("DELETE FROM ir_model_data WHERE module = 'sol_demo' AND model = 'medilab.parameter.method.machine'")
    # ICP-MS now measures lead, cadmium and arsenic of 20 samples in one 4-hour load. Cadmium, which the demo archived
    # as an example, is tested again; mercury takes its place.
    cr.execute(
        """
        UPDATE medilab_machine_method SET duration_minutes = 240, capacity = 20
         WHERE id = (SELECT res_id FROM ir_model_data WHERE module = 'sol_demo' AND name = 'demo_machine_method_icpms_metals')
        """
    )
    cr.execute(
        """
        UPDATE medilab_test_parameter SET active = TRUE
         WHERE id = (SELECT res_id FROM ir_model_data WHERE module = 'sol_demo' AND name = 'demo_test_parameter_cadmium')
        """
    )

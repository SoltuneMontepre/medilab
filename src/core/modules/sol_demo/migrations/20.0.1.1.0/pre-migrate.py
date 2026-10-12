def migrate(cr, version):
    # The demo departments are Odoo departments now, named after hr.department.
    cr.execute(
        "UPDATE ir_model_data SET name = replace(name, 'demo_department_', 'demo_hr_department_') "
        r"WHERE module = 'sol_demo' AND model = 'hr.department' AND name LIKE 'demo\_department\_%'"
    )

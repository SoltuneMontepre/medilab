from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tools.sql import set_not_null, table_exists

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_EMPLOYEE
from odoo.addons.sol_laboratory.constants.permissions import SCOPE_DOMAINS

OLD_DEPARTMENT_MODEL = "medilab.department"
OLD_OWN_DEPARTMENT_DOMAIN = "[('department_id.person_ids', 'any', [('user_id', '=', user.id), ('active', '=', True)])]"


def migrate(cr, version):
    # Departments move to Odoo's hr.department and people delegate to an Odoo employee, keeping their links.
    if not table_exists(cr, "medilab_department"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    departments = _move_departments(env)
    _move_people(env, departments)
    _move_permissions(env)
    cr.execute("ALTER TABLE medilab_parameter_method DROP COLUMN medilab_department_id")
    cr.execute("ALTER TABLE medilab_person DROP COLUMN partner_id, DROP COLUMN user_id, DROP COLUMN department_id")
    cr.execute("DROP TABLE medilab_department")
    env.transaction.invalidate_ormcache()


def _move_departments(env):
    env.cr.execute("SELECT id, name, active FROM medilab_department ORDER BY id")
    departments = {}
    for old_id, name, active in env.cr.fetchall():
        department = env[MODEL_DEPARTMENT].create({"name": name, "active": active})
        departments[old_id] = department.id
        env.cr.execute(
            "UPDATE ir_model_data SET model = %s, res_id = %s WHERE model = %s AND res_id = %s",
            (MODEL_DEPARTMENT, department.id, OLD_DEPARTMENT_MODEL, old_id),
        )
        env.cr.execute(
            "UPDATE medilab_parameter_method SET department_id = %s WHERE medilab_department_id = %s",
            (department.id, old_id),
        )
    return departments


def _move_people(env, departments):
    env.cr.execute("SELECT id, partner_id, user_id, department_id, active FROM medilab_person ORDER BY id")
    employees = env[MODEL_EMPLOYEE]
    for person_id, partner_id, user_id, department_id, active in env.cr.fetchall():
        values = {"active": active, "work_contact_id": partner_id}
        if department_id:
            values["department_id"] = departments[department_id]
        # A user may already have an employee, such as the one Odoo's demo data gives the default administrator.
        employee = env["res.users"].browse(user_id).employee_id
        if employee:
            employee.write(values)
        else:
            name = env["res.partner"].browse(partner_id).name
            employee = employees.create({"name": name, "user_id": user_id, **values})
        env.cr.execute("UPDATE medilab_person SET employee_id = %s WHERE id = %s", (employee.id, person_id))
    set_not_null(env.cr, "medilab_person", "employee_id")


def _move_permissions(env):
    env.cr.execute(
        "UPDATE medilab_permission SET document_model = %s WHERE document_model = %s",
        (MODEL_DEPARTMENT, OLD_DEPARTMENT_MODEL),
    )
    env.cr.execute(
        "UPDATE ir_access SET model_id = %s WHERE model_id = (SELECT id FROM ir_model WHERE model = %s)",
        (env["ir.model"]._get_id(MODEL_DEPARTMENT), OLD_DEPARTMENT_MODEL),
    )
    env.cr.execute(
        "UPDATE ir_access SET domain = %s WHERE domain = %s",
        (SCOPE_DOMAINS["own_department"], OLD_OWN_DEPARTMENT_DOMAIN),
    )

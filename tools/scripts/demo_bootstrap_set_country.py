# ruff: noqa: F821
company = env.ref("base.main_company")
vietnam = env.ref("base.vn")
company.partner_id.country_id = vietnam
env.cr.flush()
company.partner_id.invalidate_recordset(["country_id"])
if company.partner_id.country_id.id != vietnam.id:
    raise RuntimeError("The main company country was not set to Vietnam.")
env.cr.commit()

# ruff: noqa: F821
company = env.ref("base.main_company")
vietnam = env.ref("base.vn")
company.partner_id.country_id = vietnam
env.cr.flush()
if company.partner_id.country_id != vietnam:
    raise RuntimeError("The main company country was not set to Vietnam.")
env.cr.commit()

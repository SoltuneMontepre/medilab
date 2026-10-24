# ruff: noqa: F821
import json

company = env.ref("base.main_company")
vietnam = env.ref("base.vn")
vnd = env.ref("base.VND")
moves = env["account.move"]
if moves.search_count([("company_id", "=", company.id)]):
    raise RuntimeError("Refusing to load a chart after accounting moves exist.")
if company.root_id._existing_accounting():
    raise RuntimeError("Refusing to replace an existing accounting foundation.")

env["account.chart.template"].try_loading("vn", company)
env.cr.flush()
company.invalidate_recordset()
if company.chart_template != "vn":
    raise RuntimeError(
        f"Expected the Vietnamese chart, got {company.chart_template!r}."
    )
if company.partner_id.country_id != vietnam:
    raise RuntimeError("The company partner country is not Vietnam.")
if company.account_fiscal_country_id != vietnam:
    raise RuntimeError("The accounting fiscal country is not Vietnam.")
if company.currency_id != vnd:
    raise RuntimeError("The Vietnamese chart did not configure VND.")

journals = env["account.journal"]
sale_journals = journals.search_count(
    [("company_id", "=", company.id), ("type", "=", "sale")]
)
purchase_journals = journals.search_count(
    [("company_id", "=", company.id), ("type", "=", "purchase")]
)
if not sale_journals or not purchase_journals:
    raise RuntimeError("The Vietnamese chart is missing sales or purchase journals.")

tax = env["account.tax"].search(
    [
        ("company_id", "=", company.id),
        ("country_id", "=", vietnam.id),
        ("type_tax_use", "=", "sale"),
    ],
    limit=1,
)
if not tax:
    raise RuntimeError("The Vietnamese chart has no company sales tax.")
for lines in (tax.invoice_repartition_line_ids, tax.refund_repartition_line_ids):
    base_lines = lines.filtered(lambda line: line.repartition_type == "base")
    if len(base_lines) != 1:
        raise RuntimeError(
            "The Vietnamese sales tax has invalid base repartition lines."
        )

env.cr.commit()
print(
    json.dumps(
        {
            "chart": company.chart_template,
            "company_country": company.partner_id.country_id.code,
            "fiscal_country": company.account_fiscal_country_id.code,
            "currency": company.currency_id.name,
            "domestic_fiscal_position": company.account_fiscal_country_id.code
            and company.domestic_fiscal_position_id.id
            or None,
            "sale_journals": sale_journals,
            "purchase_journals": purchase_journals,
            "tax_country": tax.country_id.code,
        },
        sort_keys=True,
    )
)

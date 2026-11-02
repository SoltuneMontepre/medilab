def migrate(cr, _version):
    # The post-migrate turned these links into scope lines, and Odoo keeps the table of a removed many2many field.
    cr.execute("DROP TABLE IF EXISTS medilab_accreditation_certificate_method_rel")

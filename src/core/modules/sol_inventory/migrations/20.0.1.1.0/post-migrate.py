def migrate(cr, _version):
    # Prepared solutions are made in the laboratory and never bought; those created before the rule are not bought
    # any more.
    cr.execute(
        """
        UPDATE product_template AS template
           SET purchase_ok = FALSE
          FROM product_product AS item
         WHERE item.product_tmpl_id = template.id
           AND item.item_kind = 'solution'
           AND template.purchase_ok
        """
    )

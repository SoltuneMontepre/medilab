def migrate(cr, _version):
    # Before the switch, a shelf life after opening above 0 days was the only way to shorten an opened container's
    # life, so those items use it.
    cr.execute(
        """
        UPDATE product_product
           SET use_shelf_life_after_opening = TRUE
         WHERE shelf_life_after_opening_days > 0
        """
    )

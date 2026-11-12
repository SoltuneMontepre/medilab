def migrate(cr, _version):
    # Odoo deletes the models 20.0.1.3.0 had and this version does not, but leaves their tables and rows behind. Their
    # foreign keys would also keep the recipes, locations and containers they name from being deleted.
    cr.execute(
        """
        DROP TABLE IF EXISTS
            medilab_container_opening,
            medilab_container_scan,
            medilab_preparation,
            medilab_preparation_make,
            medilab_preparation_make_container,
            medilab_preparation_make_line,
            medilab_preparation_make_stock_scrap_reason_tag_rel,
            medilab_result_container,
            medilab_stock_correction,
            medilab_stock_relocation,
            medilab_stock_use,
            medilab_stock_use_stock_scrap_reason_tag_rel
        CASCADE
        """
    )
    # A container's item and lot are computed again; Odoo keeps the columns that stored them.
    cr.execute("ALTER TABLE stock_package DROP COLUMN IF EXISTS item_id, DROP COLUMN IF EXISTS lot_id")
